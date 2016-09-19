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

from senlin.common import constraints
from senlin.common import consts
from senlin.common.i18n import _
from senlin.common import scaleutils
from senlin.common import schema
from senlin.engine import health_manager
from senlin.objects import cluster as co
from senlin.policies import base


class HealthPolicy(base.Policy):
    """Policy for health management of a cluster."""

    VERSION = '1.0'

    PRIORITY = 600

    TARGET = [
        ('BEFORE', consts.CLUSTER_CHECK),
        ('BEFORE', consts.CLUSTER_DEL_NODES),
        ('BEFORE', consts.CLUSTER_RECOVER),
        ('BEFORE', consts.CLUSTER_RESIZE),
        ('BEFORE', consts.CLUSTER_SCALE_IN),
        ('BEFORE', consts.NODE_DELETE),
        ('AFTER', consts.CLUSTER_DEL_NODES),
        ('AFTER', consts.CLUSTER_SCALE_IN),
        ('AFTER', consts.CLUSTER_RESIZE),
        ('AFTER', consts.NODE_DELETE),
    ]

    # Should be ANY if profile provides health check support?
    PROFILE_TYPE = [
        'os.nova.server',
        'os.heat.stack',
    ]

    KEYS = (DETECTION, RECOVERY) = ('detection', 'recovery')

    _DETECTION_KEYS = (
        DETECTION_TYPE, DETECTION_OPTIONS,
    ) = (
        'type', 'options'
    )

    DETECTION_TYPES = (
        VM_LIFECYCLE_EVENTS, NODE_STATUS_POLLING,
        # LB_STATUS_POLLING,
    ) = (
        'VM_LIFECYCLE_EVENTS', 'NODE_STATUS_POLLING',
        # 'LB_STATUS_POLLING',
    )

    _DETECTION_OPTIONS = (
        DETECTION_INTERVAL,
    ) = (
        'interval',
    )

    _RECOVERY_KEYS = (
        RECOVERY_ACTIONS, RECOVERY_FENCING
    ) = (
        'actions', 'fencing'
    )

    RECOVERY_ACTION_VALUES = (
        REBUILD, RECREATE,
        # REBOOT, MIGRATE, EVACUATE,
    ) = (
        "REBUILD", "RECREATE",
        # 'REBOOT', 'MIGRATE', 'EVACUATE',
    )

    FENCING_OPTION_VALUES = (
        COMPUTE,
        # STORAGE, NETWORK,
    ) = (
        'COMPUTE',
        # 'STORAGE', 'NETWORK'
    )

    properties_schema = {
        DETECTION: schema.Map(
            _('Policy aspect for node failure detection.'),
            schema={
                DETECTION_TYPE: schema.String(
                    _('Type of node failure detection.'),
                    constraints=[
                        constraints.AllowedValues(DETECTION_TYPES),
                    ],
                    required=True,
                ),
                DETECTION_OPTIONS: schema.Map(
                    schema={
                        DETECTION_INTERVAL: schema.Integer(
                            _("Number of seconds between pollings. Only "
                              "required when type is 'NODE_STATUS_POLLING'."),
                            default=60,
                        ),
                    }
                ),
            },
            required=True,
        ),

        RECOVERY: schema.Map(
            _('Policy aspect for node failure recovery.'),
            schema={
                RECOVERY_ACTIONS: schema.List(
                    _('List of actions to try for node recovery.'),
                    schema=schema.String(
                        _('Action to try for node recovery.'),
                        constraints=[
                            constraints.AllowedValues(RECOVERY_ACTION_VALUES),
                        ]
                    ),
                ),
                RECOVERY_FENCING: schema.List(
                    _('List of services to be fenced.'),
                    schema=schema.String(
                        _('Service to be fenced.'),
                        constraints=[
                            constraints.AllowedValues(FENCING_OPTION_VALUES),
                        ],
                    ),
                ),
            }
        ),
    }

    def __init__(self, name, spec, **kwargs):
        super(HealthPolicy, self).__init__(name, spec, **kwargs)

        self.check_type = self.properties[self.DETECTION][self.DETECTION_TYPE]
        options = self.properties[self.DETECTION][self.DETECTION_OPTIONS]
        self.interval = options[self.DETECTION_INTERVAL]
        recover_settings = self.properties[self.RECOVERY]
        self.recover_actions = recover_settings[self.RECOVERY_ACTIONS]
        self.fencing_types = recover_settings[self.RECOVERY_FENCING]

    def attach(self, cluster):
        """"Hook for policy attach.

        Register the cluster for health management.

        :param cluster: The target cluster.
        :return: A tuple comprising execution result and policy data.
        """
        kwargs = {
            'check_type': self.check_type,
            'interval': self.interval,
            'params': {},
        }

        health_manager.register(cluster.id, engine_id=None, **kwargs)

        data = {
            'check_type': self.check_type,
            'interval': self.interval,
        }

        return True, self._build_policy_data(data)

    def detach(self, cluster):
        """Hook for policy detach.

        Unregister the cluster for health management.
        :param cluster: The target cluster.
        :returns: A tuple comprising the execution result and reason.
        """
        health_manager.unregister(cluster.id)
        return True, ''

    def pre_op(self, cluster_id, action, **args):
        """Hook before action execution.

        One of the task for this routine is to disable health policy if the
        action is a request that will shrink the cluster. The reason is that
        the policy may attempt to recover nodes that are to be deleted.

        :param cluster_id: The ID of the target cluster.
        :param action: The action to be examined.
        :param kwargs args: Other keyword arguments to be checked.
        :returns: Boolean indicating whether the checking passed.
        """
        if action.action in (consts.CLUSTER_SCALE_IN,
                             consts.CLUSTER_DEL_NODES,
                             consts.NODE_DELETE):
            health_manager.disable(cluster_id)
            return True

        if action.action == consts.CLUSTER_RESIZE:
            deletion = action.data.get('deletion', None)
            if deletion:
                health_manager.disable(cluster_id)
                return True

            db_cluster = co.Cluster.get(action.context, cluster_id,
                                        project_safe=True)
            res, reason = scaleutils.parse_resize_params(action, db_cluster)
            if res == base.CHECK_ERROR:
                action.data['status'] = base.CHECK_ERROR
                action.data['reason'] = reason
                return False

            if action.data.get('deletion', None):
                health_manager.disable(cluster_id)
                return True

        pd = {
            'recover_action': self.recover_actions,
            'fencing': self.fencing_types,
        }
        action.data.update({'health': pd})
        action.store(action.context)

        return True

    def post_op(self, cluster_id, action, **args):
        """Hook before action execution.

        One of the task for this routine is to re-enable health policy if the
        action is a request that will shrink the cluster thus the policy has
        been temporarily disabled.

        :param cluster_id: The ID of the target cluster.
        :param action: The action to be examined.
        :param kwargs args: Other keyword arguments to be checked.
        :returns: Boolean indicating whether the checking passed.
        """
        if action.action in (consts.CLUSTER_SCALE_IN,
                             consts.CLUSTER_DEL_NODES,
                             consts.NODE_DELETE):
            health_manager.enable(cluster_id)
            return True

        if action.action == consts.CLUSTER_RESIZE:
            deletion = action.data.get('deletion', None)
            if deletion:
                health_manager.enable(cluster_id)
                return True

            db_cluster = co.Cluster.get(action.context, cluster_id,
                                        project_safe=True)
            res, reason = scaleutils.parse_resize_params(action, db_cluster)
            if res == base.CHECK_ERROR:
                action.data['status'] = base.CHECK_ERROR
                action.data['reason'] = reason
                return False

            if action.data.get('deletion', None):
                health_manager.enable(cluster_id)
                return True

        return True
