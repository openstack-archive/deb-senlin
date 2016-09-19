#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_config import cfg

from rally import consts
from rally.plugins.openstack import scenario
from rally.plugins.openstack.scenarios.senlin import utils as senlin_utils
from rally.task import atomic
from rally.task import utils
from rally.task import validation

CONF = cfg.CONF


class SenlinPlugin(senlin_utils.SenlinScenario):
    """Base class for Senlin scenarios with basic atomic actions."""

    @atomic.action_timer("senlin.get_action")
    def _get_action(self, action_id):
        """Get action details.

        :param action_id: ID of action to get

        :returns: object of action
        """
        return self.admin_clients("senlin").get_action(action_id)

    @atomic.action_timer("senlin.resize_cluster")
    def _resize_cluster(self, cluster, adj_type=None, number=None,
                        min_size=None, max_size=None, min_step=None,
                        strict=True):
        """Adjust cluster size.

        :param cluster: cluster object to resize.
        :param adj_type: type of adjustment. If specified, must be one of the
                         strings defined in `consts.ADJUSTMENT_TYPES`.
        :param number: number for adjustment. It is interpreted as the new
                       desired_capacity of the cluster if `adj_type` is set
                       to `EXACT_CAPACITY`; it is interpreted as the relative
                       number of nodes to add/remove when `adj_type` is set
                       to `CHANGE_IN_CAPACITY`; it is treated as a percentage
                       when `adj_type` is set to `CHANGE_IN_PERCENTAGE`.
        :param min_size: new lower bound of the cluster size, if specified.
        :param max_size: new upper bound of the cluster size, if specified.
                         A value of negative means no upper limit is imposed.
        :param min_step: the number of nodes to be added or removed when
                         `adj_type` is set to value `CHANGE_IN_PERCENTAGE`
                         and the number calculated is less than 1.
        :param strict: whether Senlin should try a best-effort style resizing
                       or just rejects the request when scaling beyond its
                       current size constraint.
        """
        kwargs = {}
        if adj_type:
            kwargs['adjustment_type'] = adj_type
        if number:
            kwargs['number'] = number
        if min_size:
            kwargs['min_size'] = min_size
        if max_size:
            kwargs['max_size'] = max_size
        if min_step:
            kwargs['min_step'] = min_step
        kwargs['strict'] = strict
        res = self.admin_clients("senlin").cluster_resize(cluster.id, **kwargs)
        action = self._get_action(res['action'])
        utils.wait_for_status(
            action,
            ready_statuses=["SUCCEEDED"],
            failure_statuses=["FAILED"],
            update_resource=self._get_action,
            timeout=senlin_utils.CONF.benchmark.senlin_action_timeout)

    @validation.required_openstack(admin=True)
    @validation.required_services(consts.Service.SENLIN)
    @scenario.configure(context={"cleanup": ["senlin"]})
    def create_resize_delete_cluster(self, profile_spec, create_params,
                                     resize_params, timeout=3600):
        """Create a cluster, resize it and then delete it.

        Measure the `senlin cluster-create`, `senlin cluster-resize`
        and `senlin cluster-delete` commands performance.

        :param profile_spec: the spec dictionary used to create profile
        :param create_params: the dictionary provides the parameters for
                              cluster creation
        :param resize_params: the dictionary provides the parameters
                              for cluster resizing
        :param timeout: The timeout value in seconds for each cluster
                        action, including creation, deletion and resizing
        """
        profile = self._create_profile(profile_spec)
        cluster = self._create_cluster(profile.id, timeout=timeout,
                                       **create_params)
        self._resize_cluster(cluster, **resize_params)
        self._delete_cluster(cluster)
        self._delete_profile(profile)
