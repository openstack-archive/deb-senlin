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

import mock
from senlin.common import consts
from senlin.common import scaleutils as su
from senlin.engine import health_manager
from senlin.objects import cluster as co
from senlin.policies import base as pb
from senlin.policies import health_policy
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


class TestHealthPolicy(base.SenlinTestCase):

    def setUp(self):
        super(TestHealthPolicy, self).setUp()
        self.context = utils.dummy_context()

        self.spec = {
            'type': 'senlin.policy.health',
            'version': '1.0',
            'properties': {
                'detection': {
                    'type': 'NODE_STATUS_POLLING',
                    'options': {
                        'interval': 60
                    }
                },
                'recovery': {
                    'fencing': ['COMPUTE'],
                    'actions': ['REBUILD']
                }
            }
        }
        cluster = mock.Mock()
        cluster.id = 'CLUSTER_ID'
        node = mock.Mock()
        node.status = 'ACTIVE'
        cluster.nodes = [node]
        self.cluster = cluster
        self.patch('senlin.rpc.client.EngineClient')
        self.hp = health_policy.HealthPolicy('test-policy', self.spec)

    def test_policy_init(self):
        self.assertIsNone(self.hp.id)
        self.assertEqual('test-policy', self.hp.name)
        self.assertEqual('senlin.policy.health-1.0', self.hp.type)
        self.assertEqual('NODE_STATUS_POLLING', self.hp.check_type)
        self.assertEqual(60, self.hp.interval)
        self.assertEqual(['REBUILD'], self.hp.recover_actions)

    @mock.patch.object(health_manager, 'register')
    def test_attach(self, mock_hm_reg):

        policy_data = {
            'HealthPolicy': {
                'data': {
                    'check_type': self.hp.check_type,
                    'interval': self.hp.interval},
                'version': '1.0'
            }
        }

        res, data = self.hp.attach(self.cluster)
        self.assertTrue(res)
        self.assertEqual(policy_data, data)
        kwargs = {
            'check_type': self.hp.check_type,
            'interval': self.hp.interval,
            'params': {},
        }
        mock_hm_reg.assert_called_once_with('CLUSTER_ID',
                                            engine_id=None,
                                            **kwargs)

    @mock.patch.object(health_manager, 'unregister')
    def test_detach(self, mock_hm_reg):
        res, data = self.hp.detach(self.cluster)
        self.assertTrue(res)
        self.assertEqual('', data)
        mock_hm_reg.assert_called_once_with('CLUSTER_ID')

    def test_pre_op_default(self):
        action = mock.Mock(context='action_context', data={},
                           action=consts.CLUSTER_RECOVER)

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertTrue(res)
        data = {
            'health': {
                'recover_action': ['REBUILD'],
                'fencing': ['COMPUTE'],
            }
        }
        self.assertEqual(data, action.data)

    @mock.patch.object(health_manager, 'disable')
    def test_pre_op_scale_in(self, mock_disable):
        action = mock.Mock(context='action_context', data={},
                           action=consts.CLUSTER_SCALE_IN)

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_disable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(health_manager, 'disable')
    def test_pre_op_cluster_del_nodes(self, mock_disable):
        action = mock.Mock(context='action_context', data={},
                           action=consts.CLUSTER_DEL_NODES)

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_disable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(health_manager, 'disable')
    def test_pre_op_node_delete(self, mock_disable):
        action = mock.Mock(context='action_context', data={},
                           action=consts.NODE_DELETE)

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_disable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(health_manager, 'disable')
    def test_pre_op_resize_with_data(self, mock_disable):
        action = mock.Mock(context='action_context', data={'deletion': 'foo'},
                           action=consts.CLUSTER_RESIZE)

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_disable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(su, 'parse_resize_params')
    @mock.patch.object(co.Cluster, 'get')
    @mock.patch.object(health_manager, 'disable')
    def test_pre_op_resize_without_data(self, mock_disable, mock_get,
                                        mock_parse):
        def fake_check(*args, **kwargs):
            action.data['deletion'] = {'foo': 'bar'}
            return pb.CHECK_OK, 'good'

        x_cluster = mock.Mock()
        mock_get.return_value = x_cluster
        action = mock.Mock(context='action_context', data={},
                           action=consts.CLUSTER_RESIZE)
        mock_parse.side_effect = fake_check

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_disable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(su, 'parse_resize_params')
    @mock.patch.object(co.Cluster, 'get')
    @mock.patch.object(health_manager, 'disable')
    def test_pre_op_resize_parse_error(self, mock_disable, mock_get,
                                       mock_parse):
        x_cluster = mock.Mock()
        mock_get.return_value = x_cluster
        action = mock.Mock(context='action_context', data={},
                           action=consts.CLUSTER_RESIZE)
        mock_parse.return_value = pb.CHECK_ERROR, 'no good'

        res = self.hp.pre_op(self.cluster.id, action)

        self.assertFalse(res)
        self.assertEqual(pb.CHECK_ERROR, action.data['status'])
        self.assertEqual('no good', action.data['reason'])
        self.assertEqual(0, mock_disable.call_count)

    def test_post_op_default(self):
        action = mock.Mock(action='FAKE_ACTION')

        res = self.hp.post_op(self.cluster.id, action)

        self.assertTrue(res)

    @mock.patch.object(health_manager, 'enable')
    def test_post_op_scale_in(self, mock_enable):
        action = mock.Mock(action=consts.CLUSTER_SCALE_IN)

        res = self.hp.post_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_enable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(health_manager, 'enable')
    def test_post_op_cluster_del_nodes(self, mock_enable):
        action = mock.Mock(action=consts.CLUSTER_DEL_NODES)

        res = self.hp.post_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_enable.assert_called_once_with(self.cluster.id)

    @mock.patch.object(health_manager, 'enable')
    def test_post_op_node_delete(self, mock_enable):
        action = mock.Mock(action=consts.NODE_DELETE)

        res = self.hp.post_op(self.cluster.id, action)

        self.assertTrue(res)
        mock_enable.assert_called_once_with(self.cluster.id)
