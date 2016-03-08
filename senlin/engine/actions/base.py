# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import six
import time

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils

from senlin.common import context as req_context
from senlin.common import exception
from senlin.common.i18n import _
from senlin.common.i18n import _LE
from senlin.db import api as db_api
from senlin.engine import cluster_policy as cp_mod
from senlin.engine import event as EVENT
from senlin.policies import base as policy_mod

wallclock = time.time
LOG = logging.getLogger(__name__)

# Action causes
CAUSES = (
    CAUSE_RPC, CAUSE_DERIVED,
) = (
    'RPC Request',
    'Derived Action',
)


class Action(object):
    '''An action can be performed on a cluster or a node of a cluster.'''

    RETURNS = (
        RES_OK, RES_ERROR, RES_RETRY, RES_CANCEL, RES_TIMEOUT,
    ) = (
        'OK', 'ERROR', 'RETRY', 'CANCEL', 'TIMEOUT',
    )

    # Action status definitions:
    #  INIT:      Not ready to be executed because fields are being modified,
    #             or dependency with other actions are being analyzed.
    #  READY:     Initialized and ready to be executed by a worker.
    #  RUNNING:   Being executed by a worker thread.
    #  SUCCEEDED: Completed with success.
    #  FAILED:    Completed with failure.
    #  CANCELLED: Action cancelled because worker thread was cancelled.
    STATUSES = (
        INIT, WAITING, READY, RUNNING, SUSPENDED,
        SUCCEEDED, FAILED, CANCELLED
    ) = (
        'INIT', 'WAITING', 'READY', 'RUNNING', 'SUSPENDED',
        'SUCCEEDED', 'FAILED', 'CANCELLED',
    )

    # Signal commands
    COMMANDS = (
        SIG_CANCEL, SIG_SUSPEND, SIG_RESUME,
    ) = (
        'CANCEL', 'SUSPEND', 'RESUME',
    )

    def __new__(cls, target, action, context, **kwargs):
        if (cls != Action):
            return super(Action, cls).__new__(cls)

        target_type = action.split('_')[0]
        if target_type == 'CLUSTER':
            from senlin.engine.actions import cluster_action
            ActionClass = cluster_action.ClusterAction
        elif target_type == 'NODE':
            from senlin.engine.actions import node_action
            ActionClass = node_action.NodeAction
        else:
            from senlin.engine.actions import custom_action
            ActionClass = custom_action.CustomAction

        return super(Action, cls).__new__(ActionClass)

    def __init__(self, target, action, context, **kwargs):
        # context will be persisted into database so that any worker thread
        # can pick the action up and execute it on behalf of the initiator

        self.id = kwargs.get('id', None)
        self.name = kwargs.get('name', '')

        self.context = context
        self.user = context.user
        self.project = context.project
        self.domain = context.domain

        # TODO(Qiming): make description a db column
        self.description = kwargs.get('description', '')

        self.action = action
        self.target = target

        # Why this action is fired, it can be a UUID of another action
        self.cause = kwargs.get('cause', '')

        # Owner can be an UUID format ID for the worker that is currently
        # working on the action.  It also serves as a lock.
        self.owner = kwargs.get('owner', None)

        # An action may need to be executed repeatitively, interval is the
        # time in seconds between two consequtive execution.
        # A value of -1 indicates that this action is only to be executed once
        self.interval = kwargs.get('interval', -1)

        # Start time can be an absolute time or a time relative to another
        # action. E.g.
        #   - '2014-12-18 08:41:39.908569'
        #   - 'AFTER: 57292917-af90-4c45-9457-34777d939d4d'
        #   - 'WHEN: 0265f93b-b1d7-421f-b5ad-cb83de2f559d'
        self.start_time = kwargs.get('start_time', None)
        self.end_time = kwargs.get('end_time', None)

        # Timeout is a placeholder in case some actions may linger too long
        self.timeout = kwargs.get('timeout', cfg.CONF.default_action_timeout)

        # Return code, useful when action is not automatically deleted
        # after execution
        self.status = kwargs.get('status', self.INIT)
        self.status_reason = kwargs.get('status_reason', '')

        # All parameters are passed in using keyword arguments which is
        # a dictionary stored as JSON in DB
        self.inputs = kwargs.get('inputs', {})
        self.outputs = kwargs.get('outputs', {})

        self.created_at = kwargs.get('created_at', None)
        self.updated_at = kwargs.get('updated_at', None)

        self.data = kwargs.get('data', {})

    def store(self, context):
        """Store the action record into database table.

        :param context: An instance of the request context.
        :return: The ID of the stored object.
        """

        timestamp = timeutils.utcnow()

        values = {
            'name': self.name,
            'context': self.context.to_dict(),
            'target': self.target,
            'action': self.action,
            'cause': self.cause,
            'owner': self.owner,
            'interval': self.interval,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'timeout': self.timeout,
            'status': self.status,
            'status_reason': self.status_reason,
            'inputs': self.inputs,
            'outputs': self.outputs,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'data': self.data,
            'user': self.user,
            'project': self.project,
            'domain': self.domain,
        }

        if self.id:
            self.updated_at = timestamp
            values['updated_at'] = timestamp
            db_api.action_update(context, self.id, values)
        else:
            self.created_at = timestamp
            values['created_at'] = timestamp
            action = db_api.action_create(context, values)
            self.id = action.id

        return self.id

    @classmethod
    def _from_db_record(cls, record):
        """Construct a action object from database record.

        :param context: the context used for DB operations;
        :param record: a DB action object that contains all fields.
        :return: An `Action` object deserialized from the DB action object.
        """
        context = req_context.RequestContext.from_dict(record.context)
        kwargs = {
            'id': record.id,
            'name': record.name,
            'cause': record.cause,
            'owner': record.owner,
            'interval': record.interval,
            'start_time': record.start_time,
            'end_time': record.end_time,
            'timeout': record.timeout,
            'status': record.status,
            'status_reason': record.status_reason,
            'inputs': record.inputs or {},
            'outputs': record.outputs or {},
            'created_at': record.created_at,
            'updated_at': record.updated_at,
            'data': record.data,
        }

        return cls(record.target, record.action, context, **kwargs)

    @classmethod
    def load(cls, context, action_id=None, db_action=None):
        """Retrieve an action from database.

        :param context: Instance of request context.
        :param action_id: An UUID for the action to deserialize.
        :param db_action: An action object for the action to deserialize.
        :return: A `Action` object instance.
        """
        if db_action is None:
            db_action = db_api.action_get(context, action_id)
            if db_action is None:
                raise exception.ActionNotFound(action=action_id)

        return cls._from_db_record(db_action)

    @classmethod
    def load_all(cls, context, filters=None, limit=None, marker=None,
                 sort=None, project_safe=True):
        """Retrieve all actions of from database.

        :param context: Instance of the request context.
        :param filters: A dict of key-value pairs for filtering the resulted
                        list of action objects.
        :param limit: A number for restricting the number of records returned.
        :param marker: The ID of the last seen action record. Only records
                       that appear after this ID will be shown.
        :param sort: A list of sorting keys (optionally with a sort dir),
                     separated by commas.
        :param project_safe: A boolean that indicates whether actions from
                             other projects will be returned as well.
        :return: A list of `Action` objects.
        """

        records = db_api.action_get_all(context, filters=filters, sort=sort,
                                        limit=limit, marker=marker,
                                        project_safe=project_safe)

        for record in records:
            yield cls._from_db_record(record)

    @classmethod
    def create(cls, context, target, action, **kwargs):
        """Create an action object.

        :param context: The requesting context.
        :param target: The ID of the target cluster/node.
        :param action: Name of the action.
        :param dict kwargs: Other keyword arguments for the action.
        :return: ID of the action created.
        """
        params = {
            'user': context.user,
            'project': context.project,
            'domain': context.domain,
            'is_admin': context.is_admin,
            'request_id': context.request_id,
            'trusts': context.trusts,
        }
        ctx = req_context.RequestContext.from_dict(params)
        obj = cls(target, action, ctx, **kwargs)
        return obj.store(context)

    @classmethod
    def delete(cls, context, action_id):
        """Delete an action from database.

        :param context: An instance of the request context.
        :param action_id: The UUID of the target action to be deleted.
        :return: Nothing.
        """
        db_api.action_delete(context, action_id)

    def signal(self, cmd):
        '''Send a signal to the action.'''
        if cmd not in self.COMMANDS:
            return

        if cmd == self.SIG_CANCEL:
            expected_statuses = (self.INIT, self.WAITING, self.READY,
                                 self.RUNNING)
        elif cmd == self.SIG_SUSPEND:
            expected_statuses = (self.RUNNING)
        else:     # SIG_RESUME
            expected_statuses = (self.SUSPENDED)

        if self.status not in expected_statuses:
            reason = _("Action (%(action)s) is in unexpected status "
                       "(%(actual)s) while expected status should be one of "
                       "(%(expected)s).") % dict(action=self.id,
                                                 expected=expected_statuses,
                                                 actual=self.status)
            EVENT.error(self.context, self, cmd, status_reason=reason)
            return

        # TODO(Yanyan Hu): use DB session here
        db_api.action_signal(self.context, self.id, cmd)

    def execute(self, **kwargs):
        '''Execute the action.

        In theory, the action encapsulates all information needed for
        execution.  'kwargs' may specify additional parameters.
        :param kwargs: additional parameters that may override the default
                       properties stored in the action record.
        '''
        return NotImplemented

    def set_status(self, result, reason=None):
        """Set action status based on return value from execute."""

        timestamp = wallclock()

        if result == self.RES_OK:
            status = self.SUCCEEDED
            db_api.action_mark_succeeded(self.context, self.id, timestamp)

        elif result == self.RES_ERROR:
            status = self.FAILED
            db_api.action_mark_failed(self.context, self.id, timestamp,
                                      reason=reason or 'ERROR')

        elif result == self.RES_TIMEOUT:
            status = self.FAILED
            db_api.action_mark_failed(self.context, self.id, timestamp,
                                      reason=reason or 'TIMEOUT')

        elif result == self.RES_CANCEL:
            status = self.CANCELLED
            db_api.action_mark_cancelled(self.context, self.id, timestamp)

        else:  # result == self.RES_RETRY:
            status = self.READY
            # Action failed at the moment, but can be retried
            # We abandon it and then notify other dispatchers to execute it
            db_api.action_abandon(self.context, self.id)

        if status == self.SUCCEEDED:
            EVENT.info(self.context, self, self.action, status, reason)
        elif status == self.READY:
            EVENT.warning(self.context, self, self.action, status, reason)
        else:
            EVENT.error(self.context, self, self.action, status, reason)

        self.status = status
        self.status_reason = reason

    def get_status(self):
        timestamp = wallclock()
        status = db_api.action_check_status(self.context, self.id, timestamp)
        self.status = status
        return status

    def is_timeout(self):
        time_lapse = wallclock() - self.start_time
        return time_lapse > self.timeout

    def _check_signal(self):
        # Check timeout first, if true, return timeout message
        if self.timeout is not None and self.is_timeout():
            EVENT.debug(self.context, self, self.action, 'TIMEOUT')
            return self.RES_TIMEOUT

        result = db_api.action_signal_query(self.context, self.id)
        return result

    def is_cancelled(self):
        return self._check_signal() == self.SIG_CANCEL

    def is_suspended(self):
        return self._check_signal() == self.SIG_SUSPEND

    def is_resumed(self):
        return self._check_signal() == self.SIG_RESUME

    def _check_result(self, name):
        """Check policy check status and generate event.

        :param name: Name of policy checked
        :return: True if the policy checking can be continued, or False if the
                 policy checking should be aborted.
        """
        # Abort policy checking if failures found
        status = 'CHECK ERROR'
        reason = _("Failed policy '%(name)s': %(reason)s."
                   ) % {'name': name, 'reason': self.data['reason']}
        if self.data['status'] == policy_mod.CHECK_OK:
            method = EVENT.debug
            status = 'CHECK OK'
            reason = self.data['reason']
        else:
            method = EVENT.error

        method(self.context, self, self.action, status, reason)

        if self.data['status'] == policy_mod.CHECK_OK:
            return True
        else:
            return False

    def policy_check(self, cluster_id, target):
        """Check all policies attached to cluster and give result.

        :param cluster_id: The ID of the cluster to which the policy is
            attached.
        :param target: A tuple of ('when', action_name)
        :return: A dictionary that contains the check result.
        """

        if target not in ['BEFORE', 'AFTER']:
            return

        # TODO(Anyone): This could use the cluster's runtime data
        bindings = cp_mod.ClusterPolicy.load_all(self.context, cluster_id,
                                                 sort='priority',
                                                 filters={'enabled': True})
        # default values
        self.data['status'] = policy_mod.CHECK_OK
        self.data['reason'] = _('Completed policy checking.')

        for pb in bindings:
            policy = policy_mod.Policy.load(self.context, pb.policy_id)
            # We record the last operation time for all policies bound to the
            # cluster, no matter that policy is only interested in the
            # "BEFORE" or "AFTER" or both.
            if target == 'AFTER':
                pb.record_last_op(self.context)

            if not policy.need_check(target, self):
                continue

            if target == 'BEFORE':
                method = getattr(policy, 'pre_op', None)
            else:  # target == 'AFTER'
                method = getattr(policy, 'post_op', None)

            if getattr(policy, 'cooldown', None):
                if pb.cooldown_inprogress(policy.cooldown):
                    self.data['status'] = policy_mod.CHECK_ERROR
                    self.data['reason'] = _('Policy %s cooldown is still '
                                            'in progress.') % policy.id
                return

            if method is not None:
                method(cluster_id, self)

            res = self._check_result(policy.name)
            if res is False:
                return
        return

    def to_dict(self):
        if self.id:
            dep_on = db_api.dependency_get_depended(self.context, self.id)
            dep_by = db_api.dependency_get_dependents(self.context, self.id)
        else:
            dep_on = []
            dep_by = []
        action_dict = {
            'id': self.id,
            'name': self.name,
            'action': self.action,
            'target': self.target,
            'cause': self.cause,
            'owner': self.owner,
            'interval': self.interval,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'interval': self.interval,
            'timeout': self.timeout,
            'status': self.status,
            'status_reason': self.status_reason,
            'inputs': self.inputs,
            'outputs': self.outputs,
            'depends_on': dep_on,
            'depended_by': dep_by,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'data': self.data,
        }
        return action_dict


# TODO(Yanyan Hu): Replace context parameter with session parameter
def ActionProc(context, action_id):
    '''Action process.'''

    # Step 1: materialize the action object
    action = Action.load(context, action_id=action_id)
    if action is None:
        LOG.error(_LE('Action "%s" could not be found.'), action_id)
        return False

    # TODO(Anyone): Remove context usage in event module
    EVENT.info(action.context, action, action.action, 'START')

    reason = 'Action completed'
    success = True
    try:
        # Step 2: execute the action
        result, reason = action.execute()
    except Exception as ex:
        # We catch exception here to make sure the following logics are
        # executed.
        result = action.RES_ERROR
        reason = six.text_type(ex)
        LOG.exception(_('Unexpected exception occurred during action '
                        '%(action)s (%(id)s) execution: %(reason)s'),
                      {'action': action.action, 'id': action.id,
                       'reason': reason})
        success = False
    finally:
        # NOTE: locks on action is eventually released here by status update
        action.set_status(result, reason)

    return success
