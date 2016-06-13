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

from senlin.engine import service
from senlin.objects import credential as co
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


class CredentialTest(base.SenlinTestCase):

    def setUp(self):
        super(CredentialTest, self).setUp()
        self.ctx = utils.dummy_context(user_id='fake_user_id',
                                       project='fake_project_id')
        self.eng = service.EngineService('host-a', 'topic-a')

    @mock.patch.object(co.Credential, 'update_or_create')
    def test_credential_create(self, mock_create):
        x_cred = 'fake_cred'

        result = self.eng.credential_create(self.ctx, x_cred)

        self.assertEqual({'cred': x_cred}, result)
        mock_create.assert_called_once_with(
            self.ctx,
            {
                'user': 'fake_user_id',
                'project': 'fake_project_id',
                'cred': {
                    'openstack': {
                        'trust': 'fake_cred'
                    }
                }
            }
        )

    @mock.patch.object(co.Credential, 'get')
    def test_credential_get(self, mock_get):
        x_data = {'openstack': {'foo': 'bar'}}
        x_cred = mock.Mock(cred=x_data)
        mock_get.return_value = x_cred

        result = self.eng.credential_get(self.ctx)

        self.assertEqual({'foo': 'bar'}, result)
        mock_get.assert_called_once_with(
            self.ctx, 'fake_user_id', 'fake_project_id')

    @mock.patch.object(co.Credential, 'get')
    def test_credential_get_not_found(self, mock_get):
        mock_get.return_value = None

        result = self.eng.credential_get(self.ctx)

        self.assertIsNone(result)
        mock_get.assert_called_once_with(
            self.ctx, 'fake_user_id', 'fake_project_id')

    @mock.patch.object(co.Credential, 'get')
    def test_credential_data_not_match(self, mock_get):
        x_cred = mock.Mock(cred={'bogkey': 'bogval'})
        mock_get.return_value = x_cred

        result = self.eng.credential_get(self.ctx)

        self.assertIsNone(result)
        mock_get.assert_called_once_with(
            self.ctx, 'fake_user_id', 'fake_project_id')

    @mock.patch.object(co.Credential, 'update')
    def test_credential_update(self, mock_update):
        x_cred = 'fake_credential'

        result = self.eng.credential_update(self.ctx, x_cred)

        self.assertEqual({'cred': x_cred}, result)
        mock_update.assert_called_once_with(
            self.ctx, 'fake_user_id', 'fake_project_id',
            {'cred': {'openstack': {'trust': x_cred}}})
