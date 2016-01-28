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

'''
Node endpoint for Senlin v1 ReST API.
'''

from webob import exc

from senlin.api.common import util
from senlin.common import consts
from senlin.common.i18n import _
from senlin.common import utils
from senlin.rpc import client as rpc_client


class NodeData(object):
    '''The data accompanying a PUT/POST request to create/update a node.'''

    PARAMS = (consts.NODE_NAME, consts.NODE_CLUSTER_ID,
              consts.NODE_PROFILE_ID, consts.NODE_ROLE,
              consts.NODE_METADATA)

    def __init__(self, data):
        self.data = data

    def name(self):
        if consts.NODE_NAME not in self.data:
            raise exc.HTTPBadRequest(_("No node name specified."))
        return self.data[consts.NODE_NAME]

    def cluster_id(self):
        return self.data.get(consts.NODE_CLUSTER_ID, None)

    def profile_id(self):
        if consts.NODE_PROFILE_ID not in self.data:
            raise exc.HTTPBadRequest(_("No profile ID provided."))
        return self.data[consts.NODE_PROFILE_ID]

    def role(self):
        return self.data.get(consts.NODE_ROLE, None)

    def metadata(self):
        return self.data.get(consts.NODE_METADATA, None)


class NodeController(object):
    '''WSGI controller for nodes resource in Senlin v1 API.'''

    REQUEST_SCOPE = 'nodes'

    def __init__(self, options):
        self.options = options
        self.rpc_client = rpc_client.EngineClient()

    def default(self, req, **args):
        raise exc.HTTPNotFound()

    @util.policy_enforce
    def index(self, req):
        filter_whitelist = {
            'status': 'mixed',
            'name': 'mixed',
        }
        param_whitelist = {
            'cluster_id': 'single',
            'limit': 'single',
            'marker': 'single',
            'sort': 'single',
            'global_project': 'single',
        }
        params = util.get_allowed_params(req.params, param_whitelist)
        filters = util.get_allowed_params(req.params, filter_whitelist)

        key = consts.PARAM_LIMIT
        if key in params:
            params[key] = utils.parse_int_param(key, params[key])

        key = consts.PARAM_GLOBAL_PROJECT
        if key in params:
            project_safe = not utils.parse_bool_param(key, params[key])
            del params[key]
            params['project_safe'] = project_safe

        if not filters:
            filters = None

        nodes = self.rpc_client.node_list(req.context, filters=filters,
                                          **params)

        return {'nodes': nodes}

    @util.policy_enforce
    def create(self, req, body):
        node_data = body.get('node')
        if node_data is None:
            raise exc.HTTPBadRequest(_("Malformed request data, missing "
                                       "'node' key in request body."))

        data = NodeData(node_data)

        node = self.rpc_client.node_create(req.context, data.name(),
                                           data.cluster_id(),
                                           data.profile_id(),
                                           data.role(), data.metadata())
        result = {
            'node': node,
            'location': '/nodes/%s' % node['id']
        }
        return result

    @util.policy_enforce
    def get(self, req, node_id):
        key = consts.PARAM_SHOW_DETAILS
        show_details = False
        if key in req.params:
            show_details = utils.parse_bool_param(key, req.params[key])

        node = self.rpc_client.node_get(req.context, node_id,
                                        show_details=show_details)
        return {'node': node}

    @util.policy_enforce
    def update(self, req, node_id, body):
        node_data = body.get('node')
        if node_data is None:
            raise exc.HTTPBadRequest(_("Malformed request data, missing "
                                       "'node' key in request body."))
        cluster_id = node_data.get(consts.NODE_CLUSTER_ID)
        if cluster_id is not None:
            raise exc.HTTPBadRequest(_("Updating cluster_id is not allowed, "
                                       "please invoke cluster add/remove "
                                       "node actions if needed."))

        name = node_data.get(consts.NODE_NAME, None)
        profile_id = node_data.get(consts.NODE_PROFILE_ID, None)
        role = node_data.get(consts.NODE_ROLE, None)
        metadata = node_data.get(consts.NODE_METADATA, None)

        node = self.rpc_client.node_update(req.context, node_id, name,
                                           profile_id, role, metadata)
        result = {
            'node': node,
            'location': '/nodes/%s' % node['id'],
        }
        return result

    @util.policy_enforce
    def delete(self, req, node_id):
        force = 'force' in req.params
        res = self.rpc_client.node_delete(req.context, node_id, force=force,
                                          cast=False)
        action_id = res.pop('action')
        result = {'location': '/actions/%s' % action_id}
        return result
