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
from oslo_config import cfg

from senlin.drivers.openstack import nova_v2
from senlin.drivers.openstack import sdk
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


class TestNovaV2(base.SenlinTestCase):

    def setUp(self):
        super(TestNovaV2, self).setUp()

        self.ctx = utils.dummy_context()
        self.conn_params = self.ctx.to_dict()
        self.mock_conn = mock.Mock()
        self.mock_create = self.patchobject(
            sdk, 'create_connection',
            return_value=self.mock_conn)
        self.compute = self.mock_conn.compute

    def test_init(self):
        d = nova_v2.NovaClient(self.conn_params)
        self.mock_create.assert_called_once_with(self.conn_params)
        self.assertEqual(self.mock_conn, d.conn)

    def test_flavor_find(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.flavor_find('foo')
        self.compute.find_flavor.assert_called_once_with('foo', False)
        self.compute.find_flavor.reset_mock()

        d.flavor_find('foo', True)
        self.compute.find_flavor.assert_called_once_with('foo', True)
        self.compute.find_flavor.reset_mock()

        d.flavor_find('foo', False)
        self.compute.find_flavor.assert_called_once_with('foo', False)

    def test_image_find(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.image_find('foo')
        self.compute.find_image.assert_called_once_with('foo', False)
        self.compute.find_image.reset_mock()

        d.image_find('foo', True)
        self.compute.find_image.assert_called_once_with('foo', True)
        self.compute.find_image.reset_mock()

        d.image_find('foo', False)
        self.compute.find_image.assert_called_once_with('foo', False)

    def test_keypair_find(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.keypair_find('foo')
        self.compute.find_keypair.assert_called_once_with('foo', False)
        self.compute.find_keypair.reset_mock()

        d.keypair_find('foo', True)
        self.compute.find_keypair.assert_called_once_with('foo', True)
        self.compute.find_keypair.reset_mock()

        d.keypair_find('foo', False)
        self.compute.find_keypair.assert_called_once_with('foo', False)

    def test_server_create(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_create(name='foo')
        self.compute.create_server.assert_called_once_with(name='foo')

    def test_server_get(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_get('foo')
        self.compute.get_server.assert_called_once_with('foo')

    def test_server_update(self):
        d = nova_v2.NovaClient(self.conn_params)
        attrs = {'mem': 2}
        d.server_update('fakeid', **attrs)
        self.compute.update_server.assert_called_once_with('fakeid', **attrs)

    def test_server_delete(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_delete('foo', True)
        self.compute.delete_server.assert_called_once_with(
            'foo', ignore_missing=True)

    def test_server_force_delete(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_force_delete('foo', True)
        self.compute.delete_server.assert_called_once_with(
            'foo', ignore_missing=True, force=True)

    def test_server_rebuild(self):
        d = nova_v2.NovaClient(self.conn_params)
        attrs = {
            'personality': '123',
            'metadata': {'k1': 'v1'}
        }
        d.server_rebuild('sid', 'new_image', 'new_name', 'new_pass', **attrs)
        self.compute.rebuild_server.assert_called_once_with(
            'sid', 'new_name', 'new_pass', image='new_image', **attrs)

    def test_server_resize(self):
        d = nova_v2.NovaClient(self.conn_params)

        res = d.server_resize('fakeid', 'new_flavor')

        self.assertEqual(d.conn.compute.resize_server.return_value, res)
        d.conn.compute.resize_server.assert_called_once_with(
            'fakeid', 'new_flavor')

    def test_server_resize_confirm(self):
        d = nova_v2.NovaClient(self.conn_params)

        res = d.server_resize_confirm('fakeid')

        self.assertEqual(d.conn.compute.confirm_resize_server.return_value,
                         res)
        d.conn.compute.confirm_resize_server.assert_called_once_with('fakeid')

    def test_server_resize_revert(self):
        d = nova_v2.NovaClient(self.conn_params)

        res = d.server_resize_revert('fakeid')

        self.assertEqual(d.conn.compute.revert_resize_server.return_value, res)
        d.conn.compute.revert_resize_server.assert_called_once_with('fakeid')

    def test_server_reboot(self):
        d = nova_v2.NovaClient(self.conn_params)

        res = d.server_reboot('fakeid', 'soft')

        target = d.conn.compute.reboot_server
        self.assertEqual(target.return_value, res)
        target.assert_called_once_with('fakeid', 'soft')

    def test_server_change_password(self):
        d = nova_v2.NovaClient(self.conn_params)

        res = d.server_change_password('fakeid', 'new_password')

        target = d.conn.compute.change_server_password
        self.assertEqual(target.return_value, res)
        target.assert_called_once_with('fakeid', 'new_password')

    def test_wait_for_server(self):
        self.compute.find_server.return_value = 'foo'

        d = nova_v2.NovaClient(self.conn_params)
        d.wait_for_server('foo', 'STATUS1', ['STATUS2'], 5, 10)
        self.compute.wait_for_server.assert_called_once_with(
            'foo', status='STATUS1', failures=['STATUS2'], interval=5, wait=10)

    def test_wait_for_server_default_value(self):
        self.compute.find_server.return_value = 'foo'

        d = nova_v2.NovaClient(self.conn_params)
        d.wait_for_server('foo', timeout=10)
        self.compute.wait_for_server.assert_called_once_with(
            'foo', status='ACTIVE', failures=['ERROR'], interval=2, wait=10)

    def test_wait_for_server_with_default_timeout(self):
        self.compute.find_server.return_value = 'foo'
        timeout = cfg.CONF.default_action_timeout

        d = nova_v2.NovaClient(self.conn_params)
        d.wait_for_server('foo')
        self.compute.wait_for_server.assert_called_once_with(
            'foo', status='ACTIVE', failures=['ERROR'], interval=2,
            wait=timeout)

    def test_wait_for_server_delete(self):
        self.compute.find_server.return_value = 'FOO'

        d = nova_v2.NovaClient(self.conn_params)
        d.wait_for_server_delete('foo', 120)
        self.compute.find_server.assert_called_once_with('foo', True)
        self.compute.wait_for_delete.assert_called_once_with('FOO', wait=120)

    def test_wait_for_server_delete_with_default_timeout(self):
        cfg.CONF.set_override('default_action_timeout', 360, enforce_type=True)
        self.compute.find_server.return_value = 'FOO'

        d = nova_v2.NovaClient(self.conn_params)
        d.wait_for_server_delete('foo')
        self.compute.find_server.assert_called_once_with('foo', True)
        self.compute.wait_for_delete.assert_called_once_with('FOO', wait=360)

    def test_wait_for_server_delete_server_doesnt_exist(self):
        self.compute.find_server.return_value = None

        d = nova_v2.NovaClient(self.conn_params)
        res = d.wait_for_server_delete('foo')
        self.assertIsNone(res)

    def test_server_interface_create(self):
        server = mock.Mock()
        d = nova_v2.NovaClient(self.conn_params)
        d.server_interface_create(server, name='foo')
        self.compute.create_server_interface.assert_called_once_with(
            server, name='foo')

    def test_server_interface_list(self):
        d = nova_v2.NovaClient(self.conn_params)
        server = mock.Mock()
        d.server_interface_list(server)
        self.compute.server_interfaces.assert_called_once_with(server)
        self.compute.server_interfaces.reset_mock()

        d.server_interface_list(server, k='v')
        self.compute.server_interfaces.assert_called_once_with(server, k='v')
        self.compute.server_interfaces.reset_mock()

    def test_server_interface_delete(self):
        server = mock.Mock()
        d = nova_v2.NovaClient(self.conn_params)
        d.server_interface_delete('foo', server, True)
        self.compute.delete_server_interface.assert_called_once_with(
            'foo', server, True)
        self.compute.delete_server_interface.reset_mock()

        d.server_interface_delete('foo', server, False)
        self.compute.delete_server_interface.assert_called_once_with(
            'foo', server, False)
        self.compute.delete_server_interface.reset_mock()

        d.server_interface_delete('foo', server)
        self.compute.delete_server_interface.assert_called_once_with(
            'foo', server, True)

    def test_server_metadata_get(self):
        server = mock.Mock()
        res_server = mock.Mock()
        res_server.metadata = {
            'k1': 'v1'
        }
        self.compute.get_server_metadata.return_value = res_server

        d = nova_v2.NovaClient(self.conn_params)
        res = d.server_metadata_get(server)
        self.compute.get_server_metadata.assert_called_once_with(server)
        self.assertEqual({'k1': 'v1'}, res)

    def test_server_metadata_update(self):
        server = mock.Mock()
        res_server = mock.Mock()
        res_server.metadata = {
            'k1': 'v1'
        }
        self.compute.get_server_metadata.return_value = res_server

        d = nova_v2.NovaClient(self.conn_params)
        d.server_metadata_update(server, {'k2': 'v2'})
        self.compute.delete_server_metadata.assert_called_once_with(
            server, ['k1'])
        self.compute.set_server_metadata.assert_called_once_with(
            server, k2='v2')

    def test_server_metadata_delete(self):
        server = mock.Mock()
        d = nova_v2.NovaClient(self.conn_params)
        d.server_metadata_delete(server, 'k1')
        self.compute.delete_server_metadata.assert_called_once_with(
            server, 'k1')

    def test_validate_azs(self):
        nc = nova_v2.NovaClient(self.conn_params)

        fake_azs = [
            {'zoneState': {'available': 1}, 'zoneName': 'AZ1'},
            {'zoneState': {'available': 1}, 'zoneName': 'AZ2'},
            {'zoneState': {'available': 1}, 'zoneName': 'AZ3'},
            {'zoneState': {'available': 1}, 'zoneName': 'AZ4'}
        ]

        self.patchobject(nc, 'availability_zone_list', return_value=fake_azs)

        result = nc.validate_azs(['AZ1', 'AZ2', 'AZ5'])
        self.assertEqual(['AZ1', 'AZ2'], result)

    def test_server_group_create(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_group_create(name='sg')
        self.compute.create_server_group.assert_called_once_with(name='sg')

    def test_server_group_delete(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_group_delete('sg', True)
        self.compute.delete_server_group.assert_called_once_with(
            'sg', ignore_missing=True)
        self.compute.delete_server_group.reset_mock()

        d.server_group_delete('sg', False)
        self.compute.delete_server_group.assert_called_once_with(
            'sg', ignore_missing=False)
        self.compute.delete_server_group.reset_mock()

        d.server_group_delete('sg')
        self.compute.delete_server_group.assert_called_once_with(
            'sg', ignore_missing=True)

    def test_server_group_find(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.server_group_find('sg')
        self.compute.find_server_group.assert_called_once_with(
            'sg', ignore_missing=True)
        self.compute.find_server_group.reset_mock()

        d.server_group_find('sg', True)
        self.compute.find_server_group.assert_called_once_with(
            'sg', ignore_missing=True)
        self.compute.find_server_group.reset_mock()

        d.server_group_find('sg', False)
        self.compute.find_server_group.assert_called_once_with(
            'sg', ignore_missing=False)

    def test_hypervisor_list(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.hypervisor_list()
        self.compute.hypervisors.assert_called_once_with()
        self.compute.hypervisors.reset_mock()

        d.hypervisor_list(k='v')
        self.compute.hypervisors.assert_called_once_with(k='v')
        self.compute.hypervisors.reset_mock()

    def test_hypervisor_get(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.hypervisor_get('k')
        self.compute.get_hypervisor.assert_called_once_with('k')

    def test_service_list(self):
        d = nova_v2.NovaClient(self.conn_params)
        d.service_list()
        self.compute.services.assert_called_once()

    def test_service_force_down(self):
        d = nova_v2.NovaClient(self.conn_params)
        services = d.service_list()
        service = services.next()
        d.service_force_down(service)
        self.compute.force_service_down.assert_called_once_with(
            service, service.host, service.binary)
