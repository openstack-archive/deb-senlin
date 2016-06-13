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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils

from senlin.common import consts
from senlin.common import exception
from senlin.common.i18n import _
from senlin.common.i18n import _LE
from senlin.common import utils
from senlin.engine import cluster_policy as cpm
from senlin.engine import node as node_mod
from senlin.objects import cluster as co
from senlin.objects import cluster_policy as cpo
from senlin.policies import base as pcb
from senlin.profiles import base as pfb

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class Cluster(object):
    """A cluster is a collection of objects of the same profile type.

    All operations are performed without further checking because the
    checkings are supposed to be done before/after/during an action is
    excuted.
    """

    STATUSES = (
        INIT, ACTIVE, CREATING, UPDATING, RESIZING, DELETING,
        CHECKING, RECOVERING, CRITICAL, ERROR, WARNING,
    ) = (
        'INIT', 'ACTIVE', 'CREATING', 'UPDATING', 'RESIZING', 'DELETING',
        'CHECKING', 'RECOVERING', 'CRITICAL', 'ERROR', 'WARNING',
    )

    def __init__(self, name, desired_capacity, profile_id,
                 context=None, **kwargs):
        '''Intialize a cluster object.

        The cluster defaults to have 0 node with no profile assigned.
        '''

        self.id = kwargs.get('id', None)
        self.name = name
        self.profile_id = profile_id

        # Initialize the fields using kwargs passed in
        self.user = kwargs.get('user', '')
        self.project = kwargs.get('project', '')
        self.domain = kwargs.get('domain', '')

        self.init_at = kwargs.get('init_at', None)
        self.created_at = kwargs.get('created_at', None)
        self.updated_at = kwargs.get('updated_at', None)

        self.min_size = (kwargs.get('min_size') or
                         consts.CLUSTER_DEFAULT_MIN_SIZE)
        self.max_size = (kwargs.get('max_size') or
                         consts.CLUSTER_DEFAULT_MAX_SIZE)
        self.desired_capacity = desired_capacity
        self.next_index = kwargs.get('next_index', 1)
        self.timeout = (kwargs.get('timeout') or
                        cfg.CONF.default_action_timeout)

        self.status = kwargs.get('status', self.INIT)
        self.status_reason = kwargs.get('status_reason', 'Initializing')
        self.data = kwargs.get('data', {})
        self.metadata = kwargs.get('metadata') or {}

        # rt is a dict for runtime data
        self.rt = {
            'profile': None,
            'nodes': [],
            'policies': []
        }

        if context is not None:
            self._load_runtime_data(context)

    def _load_runtime_data(self, context):
        if self.id is None:
            return

        policies = []
        bindings = cpo.ClusterPolicy.get_all(context, self.id)
        for b in bindings:
            # Detect policy type conflicts
            policy = pcb.Policy.load(context, b.policy_id)
            policies.append(policy)

        self.rt = {
            'profile': pfb.Profile.load(context, profile_id=self.profile_id,
                                        project_safe=False),
            'nodes': node_mod.Node.load_all(context, cluster_id=self.id),
            'policies': policies
        }

    def store(self, context):
        '''Store the cluster in database and return its ID.

        If the ID already exists, we do an update.
        '''

        values = {
            'name': self.name,
            'profile_id': self.profile_id,
            'user': self.user,
            'project': self.project,
            'domain': self.domain,
            'init_at': self.init_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'min_size': self.min_size,
            'max_size': self.max_size,
            'desired_capacity': self.desired_capacity,
            'next_index': self.next_index,
            'timeout': self.timeout,
            'status': self.status,
            'status_reason': self.status_reason,
            'meta_data': self.metadata,
            'data': self.data,
        }

        timestamp = timeutils.utcnow(True)
        if self.id:
            values['updated_at'] = timestamp
            co.Cluster.update(context, self.id, values)
        else:
            self.init_at = timestamp
            values['init_at'] = timestamp
            cluster = co.Cluster.create(context, values)
            self.id = cluster.id

        self._load_runtime_data(context)
        return self.id

    @classmethod
    def _from_object(cls, context, obj):
        """Construct a cluster from database object.

        :param context: the context used for DB operations;
        :param obj: a DB cluster object that will receive all fields;
        """
        kwargs = {
            'id': obj.id,
            'user': obj.user,
            'project': obj.project,
            'domain': obj.domain,
            'init_at': obj.init_at,
            'created_at': obj.created_at,
            'updated_at': obj.updated_at,
            'min_size': obj.min_size,
            'max_size': obj.max_size,
            'next_index': obj.next_index,
            'timeout': obj.timeout,
            'status': obj.status,
            'status_reason': obj.status_reason,
            'data': obj.data,
            'metadata': obj.metadata,
        }

        return cls(obj.name, obj.desired_capacity, obj.profile_id,
                   context=context, **kwargs)

    @classmethod
    def load(cls, context, cluster_id=None, dbcluster=None, project_safe=True):
        '''Retrieve a cluster from database.'''
        if dbcluster is None:
            dbcluster = co.Cluster.get(context, cluster_id,
                                       project_safe=project_safe)
            if dbcluster is None:
                raise exception.ClusterNotFound(cluster=cluster_id)

        return cls._from_object(context, dbcluster)

    @classmethod
    def load_all(cls, context, limit=None, marker=None, sort=None,
                 filters=None, project_safe=True):
        """Retrieve all clusters from database."""

        objs = co.Cluster.get_all(context, limit=limit, marker=marker,
                                  sort=sort, filters=filters,
                                  project_safe=project_safe)

        for obj in objs:
            cluster = cls._from_object(context, obj)
            yield cluster

    def to_dict(self):
        info = {
            'id': self.id,
            'name': self.name,
            'profile_id': self.profile_id,
            'user': self.user,
            'project': self.project,
            'domain': self.domain,
            'init_at': utils.format_time(self.init_at),
            'created_at': utils.format_time(self.created_at),
            'updated_at': utils.format_time(self.updated_at),
            'min_size': self.min_size,
            'max_size': self.max_size,
            'desired_capacity': self.desired_capacity,
            'timeout': self.timeout,
            'status': self.status,
            'status_reason': self.status_reason,
            'metadata': self.metadata,
            'data': self.data,
            'nodes': [node.id for node in self.rt['nodes']],
            'policies': [policy.id for policy in self.rt['policies']],
        }
        if self.rt['profile']:
            info['profile_name'] = self.rt['profile'].name
        else:
            info['profile_name'] = None

        return info

    def set_status(self, context, status, reason=None, **kwargs):
        """Set status of the cluster.

        :param context: A DB session for accessing the backend database.
        :param status: A string providing the new status of the cluster.
        :param reason: A string containing the reason for the status change.
                       It can be omitted when invoking this method.
        :param dict kwargs: Other optional attributes to be updated.
        :returns: Nothing.
        """

        values = {}
        now = timeutils.utcnow(True)
        if status == self.ACTIVE and self.status == self.CREATING:
            self.created_at = now
            values['created_at'] = now
        elif (status == self.ACTIVE and
              self.status in (self.UPDATING, self.RESIZING)):
            self.updated_at = now
            values['updated_at'] = now

        self.status = status
        values['status'] = status
        if reason:
            self.status_reason = reason
            values['status_reason'] = reason

        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
                values[k] = v

        # There is a possibility that the profile id is changed
        if 'profile_id' in values:
            profile = pfb.Profile.load(context, profile_id=self.profile_id)
            self.rt['profile'] = profile
        co.Cluster.update(context, self.id, values)
        return

    def do_create(self, context, **kwargs):
        '''Additional logic at the beginning of cluster creation process.

        Set cluster status to CREATING.
        '''
        if self.status != self.INIT:
            LOG.error(_LE('Cluster is in status "%s"'), self.status)
            return False

        self.set_status(context, self.CREATING, reason='Creation in progress')
        return True

    def do_delete(self, context, **kwargs):
        """Additional logic at the end of cluster deletion process."""

        co.Cluster.delete(context, self.id)
        return True

    def do_update(self, context, **kwargs):
        '''Additional logic at the beginning of cluster updating progress.

        This method is intended to be called only from an action.
        '''
        self.set_status(context, self.UPDATING, reason='Update in progress')
        return True

    def do_check(self, context, **kwargs):
        '''Additional logic at the beginning of cluster checking process.

        Set cluster status to CHECKING.
        '''
        self.set_status(context, self.CHECKING, reason=_('Check in progress'))
        return True

    def do_recover(self, context, **kwargs):
        '''Additional logic at the beginning of cluster recovering process.

        Set cluster status to RECOVERING.
        '''
        self.set_status(context, self.RECOVERING,
                        reason=_('Recovery in progress'))
        return True

    def attach_policy(self, ctx, policy_id, values):
        """Attach policy object to the cluster.

        Note this method MUST be called with the cluster locked.

        :param ctx: A context for DB operation.
        :param policy_id: ID of the policy object.
        :param values: Optional dictionary containing binding properties.

        :returns: A tuple containing a boolean result and a reason string.
        """

        policy = pcb.Policy.load(ctx, policy_id)
        # Check if policy has already been attached
        for existing in self.rt['policies']:
            # Policy already attached
            if existing.id == policy_id:
                return True, _('Policy already attached.')

            # Detect policy type conflicts
            if (existing.type == policy.type) and policy.singleton:
                reason = _('Only one instance of policy type (%(ptype)s) can '
                           'be attached to a cluster, but another instance '
                           '(%(existing)s) is found attached to the cluster '
                           '(%(cluster)s) already.'
                           ) % {'ptype': policy.type,
                                'existing': existing.id,
                                'cluster': self.id}
                return False, reason

        # invoke policy callback
        res, data = policy.attach(self)
        if not res:
            return False, data

        kwargs = {
            'enabled': values['enabled'],
            'data': data,
            'priority': policy.PRIORITY
        }

        cp = cpm.ClusterPolicy(self.id, policy_id, **kwargs)
        cp.store(ctx)

        # refresh cached runtime
        self.rt['policies'].append(policy)

        return True, _('Policy attached.')

    def update_policy(self, ctx, policy_id, **values):
        """Update a policy that is already attached to a cluster.

        Note this method must be called with the cluster locked.
        :param ctx: A context for DB operation.
        :param policy_id: ID of the policy object.
        :param values: Optional dictionary containing new binding properties.

        :returns: A tuple containing a boolean result and a string reason.
        """
        # Check if policy has already been attached
        found = False
        for existing in self.policies:
            if existing.id == policy_id:
                found = True
                break
        if not found:
            return False, _('Policy not attached.')

        enabled = values.get('enabled', None)
        if enabled is None:
            return True, _('No update is needed.')

        params = {'enabled': bool(enabled)}

        cpo.ClusterPolicy.update(ctx, self.id, policy_id, params)
        return True, _('Policy updated.')

    def detach_policy(self, ctx, policy_id):
        """Detach policy object from the cluster.

        Note this method MUST be called with the cluster locked.

        :param ctx: A context for DB operation.
        :param policy_id: ID of the policy object.

        :returns: A tuple containing a boolean result and a reason string.
        """
        # Check if policy has already been attached
        found = None
        for existing in self.policies:
            if existing.id == policy_id:
                found = existing
                break
        if found is None:
            return False, _('Policy not attached.')

        policy = pcb.Policy.load(ctx, policy_id)
        res, reason = policy.detach(self)
        if not res:
            return res, reason

        cpo.ClusterPolicy.delete(ctx, self.id, policy_id)
        self.rt['policies'].remove(found)

        return True, _('Policy detached.')

    @property
    def nodes(self):
        return self.rt['nodes']

    def add_node(self, node):
        """Append specified node to the cluster cache.

        :param node: The node to become a new member of the cluster.
        """
        self.rt['nodes'].append(node)

    def remove_node(self, node_id):
        """Remove node with specified ID from cache.

        :param node_id: ID of the node to be removed from cache.
        """
        for node in self.rt['nodes']:
            if node.id == node_id:
                self.rt['nodes'].remove(node)

    @property
    def policies(self):
        return self.rt['policies']

    def get_region_distribution(self, regions):
        """Get node distribution regarding given regions.

        :param regions: list of region names to check.
        :return: a dict containing region and number as key value pairs.
        """
        dist = dict.fromkeys(regions, 0)

        for node in self.nodes:
            placement = node.data.get('placement', {})
            if placement:
                region = placement.get('region_name', None)
                if region and region in regions:
                    dist[region] += 1

        return dist

    def get_zone_distribution(self, ctx, zones):
        """Get node distribution regarding the given the availability zones.

        The availability zone information is only available for some profiles.

        :param ctx: context used to access node details.
        :param zones: list of zone names to check.
        :returns: a dict containing zone and number as key-value pairs.
        """
        dist = dict.fromkeys(zones, 0)

        for node in self.nodes:
            placement = node.data.get('placement', {})
            if placement and 'zone' in placement:
                zone = placement['zone']
                dist[zone] += 1
            else:
                details = node.get_details(ctx)
                zname = details.get('OS-EXT-AZ:availability_zone', None)
                if zname and zname in dist:
                    dist[zname] += 1

        return dist

    def nodes_by_region(self, region):
        """Get list of nodes that belong to the specified region.

        :param region: Name of region for filtering.
        :return: A list of nodes that are from the specified region.
        """
        result = []
        for node in self.nodes:
            placement = node.data.get('placement', {})
            if placement and 'region_name' in placement:
                if region == placement['region_name']:
                    result.append(node)
        return result

    def nodes_by_zone(self, zone):
        """Get list of nodes that reside in the specified availability zone.

        :param zone: Name of availability zone for filtering.
        :return: A list of nodes that reside in the specified AZ.
        """
        # TODO(anyone): Improve this to do a forced refresh via get_details?
        result = []
        for node in self.nodes:
            placement = node.data.get('placement', {})
            if placement and 'zone' in placement:
                if zone == placement['zone']:
                    result.append(node)
        return result
