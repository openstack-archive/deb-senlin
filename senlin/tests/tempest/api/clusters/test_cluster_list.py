# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from tempest.lib import decorators

from senlin.tests.tempest.api import base
from senlin.tests.tempest.common import utils


class TestClusterList(base.BaseSenlinAPITest):

    def setUp(self):
        super(TestClusterList, self).setUp()
        profile_id = utils.create_a_profile(self)
        self.addCleanup(utils.delete_a_profile, self, profile_id)

        self.cluster_id = utils.create_a_cluster(self, profile_id)
        self.addCleanup(utils.delete_a_cluster, self, self.cluster_id)

    @decorators.idempotent_id('943cdc02-81bd-4200-a08d-bc1932d932f7')
    def test_cluster_list(self):
        res = self.client.list_objs('clusters')

        # Verify resp of cluster list API
        self.assertEqual(200, res['status'])
        self.assertIsNone(res['location'])
        self.assertIsNotNone(res['body'])
        clusters = res['body']
        cluster_ids = []
        for cluster in clusters:
            for key in ['created_at', 'data', 'desired_capacity', 'domain',
                        'id', 'init_at', 'max_size', 'metadata', 'min_size',
                        'name', 'nodes', 'policies', 'profile_id',
                        'profile_name', 'project', 'status', 'status_reason',
                        'timeout', 'updated_at', 'user']:
                self.assertIn(key, cluster)
            cluster_ids.append(cluster['id'])

        self.assertIn(self.cluster_id, cluster_ids)
