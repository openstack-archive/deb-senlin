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

"""Health Manager.

Health Manager is responsible for monitoring the health of the clusters and
trigger corresponding actions to recover the clusters based on the pre-defined
health policies.
"""

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_service import service
from oslo_service import threadgroup

from senlin.common import consts
from senlin.common import context
from senlin.common.i18n import _LI, _LW
from senlin.common import messaging as rpc
from senlin import objects
from senlin.rpc import client as rpc_client

LOG = logging.getLogger(__name__)


class NotificationEndpoint(object):

    VM_FAILURE_EVENTS = {
        'compute.instance.delete.end': 'DELETE',
        'compute.instance.pause.end': 'PAUSE',
        'compute.instance.power_off.end': 'POWER_OFF',
        'compute.instance.rebuild.error': 'REBUILD',
        'compute.instance.shutdown.end': 'SHUTDOWN',
        'compute.instance.soft_delete.end': 'SOFT_DELETE',
    }

    def __init__(self, project_id, cluster_id):
        self.filter_rule = messaging.NotificationFilter(
            publisher_id='^compute.*',
            event_type='^compute\.instance\..*',
            context={'project_id': '^%s$' % project_id})
        self.project_id = project_id
        self.cluster_id = cluster_id
        self.rpc = rpc_client.EngineClient()

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        meta = payload['metadata']
        if meta.get('cluster_id') == self.cluster_id:
            if event_type not in self.VM_FAILURE_EVENTS:
                return
            params = {
                'event': self.VM_FAILURE_EVENTS[event_type],
                'state': payload.get('state', 'Unknown'),
                'instance_id': payload.get('instance_id', 'Unknown'),
                'timestamp': metadata['timestamp'],
                'publisher': publisher_id,
            }
            node_id = meta.get('cluster_node_id')
            if node_id:
                LOG.info(_LI("Requesting node recovery: %s"), node_id)
                ctx_value = context.get_service_context(
                    project=self.project_id, user=payload['user_id'])
                ctx = context.RequestContext(**ctx_value)
                self.rpc.node_recover(ctx, node_id, params)

    def warn(self, ctxt, publisher_id, event_type, payload, metadata):
        meta = payload.get('metadata', {})
        if meta.get('cluster_id') == self.cluster_id:
            LOG.warning("publisher=%s" % publisher_id)
            LOG.warning("event_type=%s" % event_type)

    def debug(self, ctxt, publisher_id, event_type, payload, metadata):
        meta = payload.get('metadata', {})
        if meta.get('cluster_id') == self.cluster_id:
            LOG.debug("publisher=%s" % publisher_id)
            LOG.debug("event_type=%s" % event_type)


def ListenerProc(exchange, project_id, cluster_id):
    transport = messaging.get_notification_transport(cfg.CONF)
    targets = [
        messaging.Target(topic='versioned_notifications', exchange=exchange),
    ]
    endpoints = [
        NotificationEndpoint(project_id, cluster_id),
    ]
    listener = messaging.get_notification_listener(
        transport, targets, endpoints, executor='threading',
        pool="senlin-listeners")

    listener.start()


class HealthManager(service.Service):

    def __init__(self, engine_service, topic, version):
        super(HealthManager, self).__init__()

        self.TG = threadgroup.ThreadGroup()
        self.engine_id = engine_service.engine_id
        self.topic = topic
        self.version = version
        self.ctx = context.get_admin_context()
        self.rpc_client = rpc_client.EngineClient()
        self.rt = {
            'registries': [],
        }

    def _dummy_task(self):
        """A Dummy task that is queued on the health manager thread group.

        The task is here so that the service always has something to wait()
        on, or else the process will exit.
        """
        pass

    def _poll_cluster(self, cluster_id):
        """Routine to be executed for polling cluster status.

        :param cluster_id: The UUID of the cluster to be checked.
        :returns: Nothing.
        """
        self.rpc_client.cluster_check(self.ctx, cluster_id)

    def _add_listener(self, cluster_id):
        """Routine to be executed for adding cluster listener.

        :param cluster_id: The UUID of the cluster to be filtered.
        :returns: Nothing.
        """
        cluster = objects.Cluster.get(self.ctx, cluster_id)
        if not cluster:
            LOG.warning(_LW("Cluster (%s) is not found."), cluster_id)
            return

        project = cluster.project
        return self.TG.add_thread(ListenerProc, 'nova', project, cluster_id)

    def _start_check(self, entry):
        """Routine for starting the checking for a cluster.

        :param entry: A dict containing the data associated with the cluster.
        :returns: An updated registry entry record.
        """
        if entry['check_type'] == consts.NODE_STATUS_POLLING:
            interval = min(entry['interval'], cfg.CONF.periodic_interval_max)
            timer = self.TG.add_timer(interval, self._poll_cluster, None,
                                      entry['cluster_id'])
            entry['timer'] = timer
        elif entry['check_type'] == consts.VM_LIFECYCLE_EVENTS:
            LOG.info(_LI("Start listening events for cluster (%s)."),
                     entry['cluster_id'])
            listener = self._add_listener(entry['cluster_id'])
            if listener:
                entry['listener'] = listener
            else:
                return None
        else:
            LOG.warning(_LW("Cluster (%(id)s) check type (%(type)s) is "
                            "invalid."),
                        {'id': entry['cluster_id'],
                         'type': entry['check_type']})
            return None

        return entry

    def _stop_check(self, entry):
        """Routine for stopping the checking for a cluster.

        :param entry: A dict containing the data associated with the cluster.
        :returns: ``None``.
        """
        timer = entry.get('timer', None)
        if timer:
            timer.stop()
            self.TG.timer_done(timer)
            return

        listener = entry.get('listener', None)
        if listener:
            self.TG.thread_done(listener)
            listener.stop()
            return

    def _load_runtime_registry(self):
        """Load the initial runtime registry with a DB scan."""
        db_registries = objects.HealthRegistry.claim(self.ctx, self.engine_id)

        for cluster in db_registries:
            entry = {
                'cluster_id': cluster.cluster_id,
                'check_type': cluster.check_type,
                'interval': cluster.interval,
                'params': cluster.params,
                'enabled': True,
            }

            LOG.info("Loading cluster %s for health monitoring",
                     cluster.cluster_id)

            entry = self._start_check(entry)
            if entry:
                self.rt['registries'].append(entry)

    def start(self):
        super(HealthManager, self).start()
        self.target = messaging.Target(server=self.engine_id, topic=self.topic,
                                       version=self.version)
        server = rpc.get_rpc_server(self.target, self)
        server.start()
        self.TG.add_timer(cfg.CONF.periodic_interval, self._dummy_task)
        self._load_runtime_registry()

    def stop(self):
        self.TG.stop_timers()
        super(HealthManager, self).stop()

    @property
    def registries(self):
        return self.rt['registries']

    def listening(self, ctx):
        """Respond to confirm that the rpc service is still alive."""
        return True

    def register_cluster(self, ctx, cluster_id, check_type, interval=None,
                         params=None):
        r"""Register cluster for health checking.

        :param ctx: The context of notify request.
        :param cluster_id: The ID of the cluster to be checked.
        :param check_type: A string indicating the type of checks.
        :param interval: An optional integer indicating the length of checking
                         periods in seconds.
        :param \*\*params: Other parameters for the health check.
        :return: None
        """
        params = params or {}

        registry = objects.HealthRegistry.create(ctx, cluster_id, check_type,
                                                 interval, params,
                                                 self.engine_id)

        entry = {
            'cluster_id': registry.cluster_id,
            'check_type': registry.check_type,
            'interval': registry.interval,
            'params': registry.params,
            'enabled': True
        }

        self._start_check(entry)
        self.rt['registries'].append(entry)

    def unregister_cluster(self, ctx, cluster_id):
        """Unregister a cluster from health checking.

        :param ctx: The context of notify request.
        :param cluster_id: The ID of the cluste to be unregistered.
        :return: None
        """
        for i in range(len(self.rt['registries']) - 1, -1, -1):
            entry = self.rt['registries'][i]
            if entry.get('cluster_id') == cluster_id:
                self._stop_check(entry)
                self.rt['registries'].pop(i)

        objects.HealthRegistry.delete(ctx, cluster_id)

    def enable_cluster(self, ctx, cluster_id, params=None):
        for c in self.rt['registries']:
            if c['cluster_id'] == cluster_id and not c['enabled']:
                c['enabled'] = True
                self._start_check(c)

    def disable_cluster(self, ctx, cluster_id, params=None):
        for c in self.rt['registries']:
            if c['cluster_id'] == cluster_id and c['enabled']:
                c['enabled'] = False
                self._stop_check(c)


def notify(engine_id, method, **kwargs):
    """Send notification to health manager service.

    :param engine_id: dispatcher to notify; broadcast if value is None
    :param method: remote method to call
    """
    timeout = cfg.CONF.engine_life_check_timeout
    client = rpc.get_rpc_client(version=consts.RPC_API_VERSION)

    if engine_id:
        # Notify specific dispatcher identified by engine_id
        call_context = client.prepare(
            version=consts.RPC_API_VERSION,
            timeout=timeout,
            topic=consts.ENGINE_HEALTH_MGR_TOPIC,
            server=engine_id)
    else:
        # Broadcast to all disptachers
        call_context = client.prepare(
            version=consts.RPC_API_VERSION,
            timeout=timeout,
            topic=consts.ENGINE_HEALTH_MGR_TOPIC)

    ctx = context.get_admin_context()

    try:
        call_context.call(ctx, method, **kwargs)
        return True
    except messaging.MessagingTimeout:
        return False


def register(cluster_id, engine_id=None, **kwargs):
    params = kwargs.pop('params', {})
    interval = kwargs.pop('interval', cfg.CONF.periodic_interval)
    check_type = kwargs.pop('check_type', consts.NODE_STATUS_POLLING)
    return notify(engine_id, 'register_cluster',
                  cluster_id=cluster_id,
                  interval=interval,
                  check_type=check_type,
                  params=params)


def unregister(cluster_id, engine_id=None):
    return notify(engine_id, 'unregister_cluster', cluster_id=cluster_id)


def enable(cluster_id, **kwargs):
    return notify(None, 'enable_cluster', cluster_id=cluster_id, params=kwargs)


def disable(cluster_id, **kwargs):
    return notify(None, 'disable_cluster', cluster_id=cluster_id,
                  params=kwargs)
