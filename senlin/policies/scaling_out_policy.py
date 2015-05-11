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

from oslo_log import log as logging

from senlin.common import constraints
from senlin.common import consts
from senlin.common.i18n import _
from senlin.common import schema
from senlin.db import api as db_api
from senlin.policies import base

LOG = logging.getLogger(__name__)


class ScalingOutPolicy(base.Policy):
    '''Policy for increasing the size of a cluster.

    This policy is expected to be enforced before the node count of a cluster
    is increased.
    '''

    __type_name__ = 'ScalingOutPolicy'

    TARGET = [
        ('BEFORE', consts.CLUSTER_SCALE_OUT),
    ]

    PROFILE_TYPE = [
        'ANY',
    ]

    KEYS = (
        ADJUSTMENT,
    ) = (
        'adjustment',
    )

    _ADJUSTMENT_KEYS = (
        ADJUSTMENT_TYPE, ADJUSTMENT_NUMBER, MIN_STEP, BEST_EFFORT,
    ) = (
        'type', 'number', 'min_step', 'best_effort',
    )

    spec_schema = {
        ADJUSTMENT: schema.Map(
            _('Detailed specification for scaling adjustments.'),
            schema={
                ADJUSTMENT_TYPE: schema.String(
                    _('Type of adjustment when scaling is triggered.'),
                    constraints=[
                        constraints.AllowedValues(consts.ADJUSTMENT_TYPES),
                    ],
                    default=consts.CHANGE_IN_CAPACITY,
                ),
                ADJUSTMENT_NUMBER: schema.Number(
                    _('A number specifying the amount of adjustment.'),
                    default=1,
                ),
                MIN_STEP: schema.Integer(
                    _('When adjustment type is set to "CHANGE_IN_PERCENTAGE",'
                      ' this specifies the cluster size will be changed by '
                      'at least this number of nodes.'),
                    default=1,
                ),
                BEST_EFFORT: schema.Boolean(
                    _('Whether do best effort scaling when new size of '
                      'cluster will break the size limitation'),
                    default=False,
                ),
            }
        ),
    }

    def __init__(self, type_name, name, **kwargs):
        super(ScalingOutPolicy, self).__init__(type_name, name, **kwargs)

        adjustment = self.spec_data[self.ADJUSTMENT]

        self.adjustment_type = adjustment[self.ADJUSTMENT_TYPE]
        self.adjustment_number = adjustment[self.ADJUSTMENT_NUMBER]
        self.adjustment_min_step = adjustment[self.MIN_STEP]
        self.best_effort = adjustment[self.BEST_EFFORT]

        # TODO(anyone): Make sure the default cooldown can be used if
        # not specified. Need support from ClusterPolicy.

    def pre_op(self, cluster_id, action, policy_data):
        cluster = db_api.cluster_get(action.context, cluster_id)
        nodes = db_api.node_get_all_by_cluster(action.context, cluster_id)
        current_size = len(nodes)

        if self.adjustment_type == consts.EXACT_CAPACITY:
            count = self.adjustment_number - current_size
        elif self.adjustment_type == consts.CHANGE_IN_CAPACITY:
            count = self.adjustment_number
        elif self.adjustment_type == consts.CHANGE_IN_PERCENTAGE:
            count = int((self.adjustment_number * current_size) / 100.0)
            if count < self.adjustment_min_step:
                count = self.adjustment_min_step

        # If action has input count, use it in prior
        count = action.inputs.get('count', count)

        # Sanity check
        if count < 0:
            policy_data.status = base.CHECK_ERROR
            policy_data.reason = _('ScalingOutPolicy generates a negative '
                                   'count for scaling out operation.')
        elif current_size + count > cluster.max_size:
            if not self.best_effort:
                policy_data.status = base.CHECK_ERROR
                policy_data.reason = _('Attempted scaling exceeds '
                                       'maximum size')
            else:
                policy_data.status = base.CHECK_OK
                count = cluster.max_size - current_size
                policy_data.reason = _('Do best effort scaling')
        else:
            policy_data.status = base.CHECK_OK
            policy_data.reason = _('Scaling request validated')

        pd = {'count': abs(count)}
        policy_data['creation'] = pd

        return policy_data
