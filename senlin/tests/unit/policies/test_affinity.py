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
from senlin.common import context
from senlin.common import exception
from senlin.common import scaleutils
from senlin.objects import cluster as co
from senlin.objects import cluster_policy as cpo
from senlin.policies import affinity_policy as ap
from senlin.policies import base as pb
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


class TestAffinityPolicy(base.SenlinTestCase):

    def setUp(self):
        super(TestAffinityPolicy, self).setUp()
        self.context = utils.dummy_context()
        self.spec = {
            'type': 'senlin.policy.affinity',
            'version': '1.0',
            'properties': {
                'servergroup': {}
            },
        }

    def test_policy_init(self):
        policy = ap.AffinityPolicy('test-policy', self.spec)
        self.assertIsNone(policy.id)
        self.assertEqual('test-policy', policy.name)
        self.assertEqual('senlin.policy.affinity-1.0', policy.type)
        self.assertFalse(policy.enable_drs)
        self.assertIsNone(policy._novaclient)

    @mock.patch("senlin.drivers.base.SenlinDriver")
    def test_nova(self, mock_driver):
        cluster = mock.Mock()
        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_params = mock.Mock()
        mock_build = self.patchobject(policy, '_build_conn_params',
                                      return_value=mock_params)
        x_driver = mock.Mock()
        mock_driver.return_value = x_driver

        result = policy.nova(cluster)

        x_nova = x_driver.compute.return_value
        self.assertEqual(x_nova, result)
        self.assertEqual(x_nova, policy._novaclient)
        mock_build.assert_called_once_with(cluster)
        x_driver.compute.assert_called_once_with(mock_params)

    def test_nova_already_initialized(self):
        cluster = mock.Mock()
        policy = ap.AffinityPolicy('test-policy', self.spec)
        x_nova = mock.Mock()
        policy._novaclient = x_nova

        result = policy.nova(cluster)

        self.assertEqual(x_nova, result)

    def test_attach_using_profile_hints(self):
        x_profile = mock.Mock()
        x_profile.type = 'os.nova.server-1.0'
        x_profile.spec = {
            'scheduler_hints': {
                'group': 'KONGFOO',
            }
        }
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_group = mock.Mock(id='GROUP_ID', policies=[u'anti-affinity'])
        x_nova = mock.Mock()
        x_nova.find_server_group.return_value = x_group

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)
        x_data = mock.Mock()
        mock_build = self.patchobject(policy, '_build_policy_data',
                                      return_value=x_data)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertEqual(x_data, data)
        self.assertTrue(res)

        mock_nova.assert_called_once_with(cluster)
        x_nova.find_server_group.assert_called_once_with('KONGFOO', True)
        mock_build.assert_called_once_with({
            'servergroup_id': 'GROUP_ID',
            'inherited_group': True
        })

    def test_attach_with_group_found(self):
        self.spec['properties']['servergroup']['name'] = 'KONGFU'
        x_profile = mock.Mock()
        x_profile.type = 'os.nova.server-1.0'
        x_profile.spec = {'foo': 'bar'}
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_group = mock.Mock(id='GROUP_ID', policies=['anti-affinity'])
        x_nova = mock.Mock()
        x_nova.find_server_group.return_value = x_group

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)
        x_data = mock.Mock()
        mock_build = self.patchobject(policy, '_build_policy_data',
                                      return_value=x_data)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual(x_data, data)

        mock_nova.assert_called_once_with(cluster)
        x_nova.find_server_group.assert_called_once_with('KONGFU', True)
        mock_build.assert_called_once_with({
            'servergroup_id': 'GROUP_ID',
            'inherited_group': True
        })

    def test_attach_with_group_not_found(self):
        self.spec['properties']['servergroup']['name'] = 'KONGFU'
        x_profile = mock.Mock()
        x_profile.spec = {'foo': 'bar'}
        x_profile.type = 'os.nova.server-1.0'
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_group = mock.Mock(id='GROUP_ID')
        x_nova = mock.Mock()
        x_nova.find_server_group.return_value = None
        x_nova.create_server_group.return_value = x_group

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)
        x_data = mock.Mock()
        mock_build = self.patchobject(policy, '_build_policy_data',
                                      return_value=x_data)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual(x_data, data)

        mock_nova.assert_called_once_with(cluster)
        x_nova.find_server_group.assert_called_once_with('KONGFU', True)
        x_nova.create_server_group.assert_called_once_with(
            name='KONGFU',
            policies=[policy.ANTI_AFFINITY])
        mock_build.assert_called_once_with({
            'servergroup_id': 'GROUP_ID',
            'inherited_group': False
        })

    def test_attach_with_group_name_not_provided(self):
        x_profile = mock.Mock()
        x_profile.spec = {'foo': 'bar'}
        x_profile.type = 'os.nova.server-1.0'
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_group = mock.Mock(id='GROUP_ID')
        x_nova = mock.Mock()
        x_nova.create_server_group.return_value = x_group

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)
        x_data = mock.Mock()
        mock_build = self.patchobject(policy, '_build_policy_data',
                                      return_value=x_data)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual(x_data, data)

        mock_nova.assert_called_once_with(cluster)
        x_nova.create_server_group.assert_called_once_with(
            name=mock.ANY,
            policies=[policy.ANTI_AFFINITY])
        mock_build.assert_called_once_with({
            'servergroup_id': 'GROUP_ID',
            'inherited_group': False
        })

    @mock.patch.object(pb.Policy, 'attach')
    def test_attach_failed_base_return_false(self, mock_attach):
        cluster = mock.Mock()
        mock_attach.return_value = (False, 'Something is wrong.')

        policy = ap.AffinityPolicy('test-policy', self.spec)

        res, data = policy.attach(cluster)

        self.assertFalse(res)
        self.assertEqual('Something is wrong.', data)

    def test_attach_failed_finding(self):
        self.spec['properties']['servergroup']['name'] = 'KONGFU'
        x_profile = mock.Mock()
        x_profile.type = 'os.nova.server-1.0'
        x_profile.spec = {'foo': 'bar'}
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_nova = mock.Mock()
        err = exception.InternalError(code=500, message='Boom')
        x_nova.find_server_group.side_effect = err

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertFalse(res)
        self.assertEqual("Failed in retrieving servergroup 'KONGFU'.", data)

        mock_nova.assert_called_once_with(cluster)
        x_nova.find_server_group.assert_called_once_with('KONGFU', True)

    def test_attach_policies_not_match(self):
        self.spec['properties']['servergroup']['name'] = 'KONGFU'
        x_profile = mock.Mock()
        x_profile.type = 'os.nova.server-1.0'
        x_profile.spec = {'foo': 'bar'}
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_group = mock.Mock(id='GROUP_ID', policies=['affinity'])
        x_nova = mock.Mock()
        x_nova.find_server_group.return_value = x_group

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertFalse(res)
        self.assertEqual("Policies specified (anti-affinity) doesn't match "
                         "that of the existing servergroup (affinity).",
                         data)

        mock_nova.assert_called_once_with(cluster)
        x_nova.find_server_group.assert_called_once_with('KONGFU', True)

    def test_attach_failed_creating_server_group(self):
        self.spec['properties']['servergroup']['name'] = 'KONGFU'
        x_profile = mock.Mock()
        x_profile.type = 'os.nova.server-1.0'
        x_profile.spec = {'foo': 'bar'}
        cluster = mock.Mock(id='CLUSTER_ID')
        cluster.rt = {'profile': x_profile}
        x_nova = mock.Mock()
        x_nova.find_server_group.return_value = None
        x_nova.create_server_group.side_effect = Exception()

        policy = ap.AffinityPolicy('test-policy', self.spec)
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)

        # do it
        res, data = policy.attach(cluster)

        # assertions
        self.assertEqual('Failed in creating servergroup.', data)
        self.assertFalse(res)

        mock_nova.assert_called_once_with(cluster)
        x_nova.find_server_group.assert_called_once_with('KONGFU', True)
        x_nova.create_server_group.assert_called_once_with(
            name=mock.ANY,
            policies=[policy.ANTI_AFFINITY])

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    @mock.patch.object(context, 'get_admin_context')
    def test_detach_inherited(self, mock_context, mock_cp):
        cluster = mock.Mock(id='CLUSTER_ID')
        x_ctx = mock.Mock()
        mock_context.return_value = x_ctx
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding
        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': True,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)

        # do it
        res, data = policy.detach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual('Servergroup resource deletion succeeded.', data)

        mock_context.assert_called_once_with()
        mock_cp.assert_called_once_with(x_ctx, 'CLUSTER_ID', 'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    @mock.patch.object(context, 'get_admin_context')
    def test_detach_not_inherited(self, mock_context, mock_cp):
        cluster = mock.Mock(id='CLUSTER_ID')
        x_ctx = mock.Mock()
        mock_context.return_value = x_ctx
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding
        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)
        x_nova = mock.Mock()
        x_nova.delete_server_group.return_value = None
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)

        # do it
        res, data = policy.detach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual('Servergroup resource deletion succeeded.', data)

        mock_context.assert_called_once_with()
        mock_cp.assert_called_once_with(x_ctx, 'CLUSTER_ID', 'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        mock_nova.assert_called_once_with(cluster)
        x_nova.delete_server_group.assert_called_once_with('SERVERGROUP_ID')

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    @mock.patch.object(context, 'get_admin_context')
    def test_detach_binding_not_found(self, mock_context, mock_cp):
        cluster = mock.Mock(id='CLUSTER_ID')
        x_ctx = mock.Mock()
        mock_context.return_value = x_ctx

        mock_cp.return_value = None

        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'

        # do it
        res, data = policy.detach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual('Servergroup resource deletion succeeded.', data)

        mock_context.assert_called_once_with()
        mock_cp.assert_called_once_with(x_ctx, 'CLUSTER_ID', 'POLICY_ID')

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    @mock.patch.object(context, 'get_admin_context')
    def test_detach_binding_data_empty(self, mock_context, mock_cp):
        cluster = mock.Mock(id='CLUSTER_ID')
        x_ctx = mock.Mock()
        mock_context.return_value = x_ctx
        x_binding = mock.Mock(data={})
        mock_cp.return_value = x_binding

        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'

        # do it
        res, data = policy.detach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual('Servergroup resource deletion succeeded.', data)

        mock_context.assert_called_once_with()
        mock_cp.assert_called_once_with(x_ctx, 'CLUSTER_ID', 'POLICY_ID')

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    @mock.patch.object(context, 'get_admin_context')
    def test_detach_policy_data_empty(self, mock_context, mock_cp):
        cluster = mock.Mock(id='CLUSTER_ID')
        x_ctx = mock.Mock()
        mock_context.return_value = x_ctx
        x_binding = mock.Mock(data={'foo': 'bar'})
        mock_cp.return_value = x_binding

        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=None)
        # do it
        res, data = policy.detach(cluster)

        # assertions
        self.assertTrue(res)
        self.assertEqual('Servergroup resource deletion succeeded.', data)

        mock_context.assert_called_once_with()
        mock_cp.assert_called_once_with(x_ctx, 'CLUSTER_ID', 'POLICY_ID')
        mock_extract.assert_called_once_with({'foo': 'bar'})

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    @mock.patch.object(context, 'get_admin_context')
    def test_detach_failing_delete_sg(self, mock_context, mock_cp):
        cluster = mock.Mock(id='CLUSTER_ID')
        x_ctx = mock.Mock()
        mock_context.return_value = x_ctx
        x_binding = mock.Mock(data={'foo': 'bar'})
        mock_cp.return_value = x_binding
        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)
        x_nova = mock.Mock()
        x_nova.delete_server_group.side_effect = Exception()
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)

        # do it
        res, data = policy.detach(cluster)

        # assertions
        self.assertFalse(res)
        self.assertEqual('Failed in deleting servergroup.', data)

        mock_context.assert_called_once_with()
        mock_cp.assert_called_once_with(x_ctx, 'CLUSTER_ID', 'POLICY_ID')
        mock_extract.assert_called_once_with({'foo': 'bar'})
        mock_nova.assert_called_once_with(cluster)
        x_nova.delete_server_group.assert_called_once_with('SERVERGROUP_ID')

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op(self, mock_cp):
        x_action = mock.Mock()
        x_action.data = {'creation': {'count': 2}}
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding

        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_cp.assert_called_once_with(x_action.context, 'CLUSTER_ID',
                                        'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        self.assertEqual(
            {
                'creation': {
                    'count': 2
                },
                'placement': {
                    'count': 2,
                    'placements': [
                        {
                            'servergroup': 'SERVERGROUP_ID'
                        },
                        {
                            'servergroup': 'SERVERGROUP_ID'
                        }
                    ]
                }
            },
            x_action.data)
        x_action.store.assert_called_once_with(x_action.context)

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op_use_scaleout_input(self, mock_cp):
        x_action = mock.Mock()
        x_action.data = {}
        x_action.action = consts.CLUSTER_SCALE_OUT
        x_action.inputs = {'count': 2}
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding

        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_cp.assert_called_once_with(x_action.context, 'CLUSTER_ID',
                                        'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        self.assertEqual(
            {
                'placement': {
                    'count': 2,
                    'placements': [
                        {
                            'servergroup': 'SERVERGROUP_ID'
                        },
                        {
                            'servergroup': 'SERVERGROUP_ID'
                        }
                    ]
                }
            },
            x_action.data)
        x_action.store.assert_called_once_with(x_action.context)

    @mock.patch.object(co.Cluster, 'get')
    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op_use_resize_params(self, mock_cp, mock_cluster):
        def fake_parse_func(action, cluster):
            action.data = {
                'creation': {
                    'count': 2
                }
            }

        x_action = mock.Mock()
        x_action.data = {}
        x_action.action = consts.CLUSTER_RESIZE
        x_action.inputs = {
            'adjustment_type': consts.EXACT_CAPACITY,
            'number': 10
        }
        x_cluster = mock.Mock()
        mock_cluster.return_value = x_cluster
        mock_parse = self.patchobject(scaleutils, 'parse_resize_params',
                                      side_effect=fake_parse_func)

        x_binding = mock.Mock()
        mock_cp.return_value = x_binding

        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_parse.assert_called_once_with(x_action, x_cluster)
        mock_cluster.assert_called_once_with(x_action.context, 'CLUSTER_ID')
        mock_cp.assert_called_once_with(x_action.context, 'CLUSTER_ID',
                                        'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        self.assertEqual(
            {
                'creation': {
                    'count': 2,
                },
                'placement': {
                    'count': 2,
                    'placements': [
                        {
                            'servergroup': 'SERVERGROUP_ID'
                        },
                        {
                            'servergroup': 'SERVERGROUP_ID'
                        }
                    ]
                }
            },
            x_action.data)
        x_action.store.assert_called_once_with(x_action.context)

    @mock.patch.object(co.Cluster, 'get')
    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op_resize_shrinking(self, mock_cp, mock_cluster):
        def fake_parse_func(action, cluster):
            action.data = {
                'deletion': {
                    'count': 2
                }
            }

        x_action = mock.Mock()
        x_action.data = {}
        x_action.action = consts.CLUSTER_RESIZE
        x_action.inputs = {
            'adjustment_type': consts.EXACT_CAPACITY,
            'number': 10
        }
        x_cluster = mock.Mock()
        mock_cluster.return_value = x_cluster
        mock_parse = self.patchobject(scaleutils, 'parse_resize_params',
                                      side_effect=fake_parse_func)
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data')

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_parse.assert_called_once_with(x_action, x_cluster)
        mock_cluster.assert_called_once_with(x_action.context, 'CLUSTER_ID')
        self.assertEqual(0, mock_cp.call_count)
        self.assertEqual(0, mock_extract.call_count)

    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op_with_zone_name(self, mock_cp):
        self.spec['properties']['availability_zone'] = 'BLUE_ZONE'
        x_action = mock.Mock()
        x_action.data = {'creation': {'count': 2}}
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding

        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_cp.assert_called_once_with(x_action.context, 'CLUSTER_ID',
                                        'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        self.assertEqual(
            {
                'creation': {
                    'count': 2
                },
                'placement': {
                    'count': 2,
                    'placements': [
                        {
                            'zone': 'BLUE_ZONE',
                            'servergroup': 'SERVERGROUP_ID'
                        },
                        {
                            'zone': 'BLUE_ZONE',
                            'servergroup': 'SERVERGROUP_ID'
                        }
                    ]
                }
            },
            x_action.data)
        x_action.store.assert_called_once_with(x_action.context)

    @mock.patch.object(co.Cluster, 'get')
    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op_with_drs_enabled(self, mock_cp, mock_cluster):
        self.spec['properties']['enable_drs_extension'] = True
        x_action = mock.Mock()
        x_action.data = {'creation': {'count': 2}}
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding

        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)
        x_cluster = mock.Mock()
        mock_cluster.return_value = x_cluster
        x_nova = mock.Mock()
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)
        x_hypervisors = [
            mock.Mock(id='HV_1', hypervisor_hostname='host1'),
            mock.Mock(id='HV_2', hypervisor_hostname='vsphere_drs1')
        ]
        x_nova.hypervisor_list.return_value = x_hypervisors
        x_hvinfo = {
            'service': {
                'host': 'drshost1'
            }
        }
        x_nova.hypervisor_get.return_value = x_hvinfo

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_cp.assert_called_once_with(x_action.context, 'CLUSTER_ID',
                                        'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        mock_cluster.assert_called_once_with(x_action.context, 'CLUSTER_ID')
        mock_nova.assert_called_once_with(x_cluster)
        x_nova.hypervisor_list.assert_called_once_with()
        x_nova.hypervisor_get.assert_called_once_with('HV_2')
        self.assertEqual(
            {
                'creation': {
                    'count': 2
                },
                'placement': {
                    'count': 2,
                    'placements': [
                        {
                            'zone': 'nova:drshost1',
                            'servergroup': 'SERVERGROUP_ID'
                        },
                        {
                            'zone': 'nova:drshost1',
                            'servergroup': 'SERVERGROUP_ID'
                        }
                    ]
                }
            },
            x_action.data)
        x_action.store.assert_called_once_with(x_action.context)

    @mock.patch.object(co.Cluster, 'get')
    @mock.patch.object(cpo.ClusterPolicy, 'get')
    def test_pre_op_with_drs_enabled_no_match(self, mock_cp, mock_cluster):
        self.spec['properties']['enable_drs_extension'] = True
        x_action = mock.Mock()
        x_action.data = {'creation': {'count': 2}}
        x_binding = mock.Mock()
        mock_cp.return_value = x_binding

        policy_data = {
            'servergroup_id': 'SERVERGROUP_ID',
            'inherited_group': False,
        }
        policy = ap.AffinityPolicy('test-policy', self.spec)
        policy.id = 'POLICY_ID'
        mock_extract = self.patchobject(policy, '_extract_policy_data',
                                        return_value=policy_data)
        x_cluster = mock.Mock()
        mock_cluster.return_value = x_cluster
        x_nova = mock.Mock()
        mock_nova = self.patchobject(policy, 'nova', return_value=x_nova)
        x_hypervisors = [
            mock.Mock(id='HV_1', hypervisor_hostname='host1'),
            mock.Mock(id='HV_2', hypervisor_hostname='host2')
        ]
        x_nova.hypervisor_list.return_value = x_hypervisors

        # do it
        policy.pre_op('CLUSTER_ID', x_action)

        mock_cp.assert_called_once_with(x_action.context, 'CLUSTER_ID',
                                        'POLICY_ID')
        mock_extract.assert_called_once_with(x_binding.data)
        mock_cluster.assert_called_once_with(x_action.context, 'CLUSTER_ID')
        mock_nova.assert_called_once_with(x_cluster)
        self.assertEqual(
            {
                'creation': {
                    'count': 2
                },
                'status': 'ERROR',
                'status_reason': 'No suitable vSphere host is available.'
            },
            x_action.data)
        x_action.store.assert_called_once_with(x_action.context)
