#
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

from webob import exc

from senlin.api.common import util
from senlin.api.common import wsgi
from senlin.common import consts
from senlin.common.i18n import _
from senlin.common import utils


class ActionData(object):
    """All required data fields for an action."""

    PARAMS = (consts.ACTION_NAME, consts.ACTION_TARGET, consts.ACTION_ACTION)

    def __init__(self, data):
        self.data = data

    def name(self):
        if consts.ACTION_NAME not in self.data:
            raise exc.HTTPBadRequest(_("No action name specified"))
        return self.data[consts.ACTION_NAME]

    def target(self):
        if consts.ACTION_TARGET not in self.data:
            raise exc.HTTPBadRequest(_("No target specified"))
        return self.data[consts.ACTION_TARGET]

    def action(self):
        if consts.ACTION_ACTION not in self.data:
            raise exc.HTTPBadRequest(_("No action specified"))
        return self.data[consts.ACTION_ACTION]

    def params(self):
        data = self.data.items()
        return dict((k, v) for k, v in data if k not in self.PARAMS)


class ActionController(wsgi.Controller):
    """WSGI controller for Actions in Senlin v1 API."""

    # Define request scope (must match what is in policy.json)
    REQUEST_SCOPE = 'actions'

    @util.policy_enforce
    def index(self, req):
        filter_whitelist = {
            consts.ACTION_NAME: 'mixed',
            consts.ACTION_TARGET: 'mixed',
            consts.ACTION_ACTION: 'mixed',
            consts.ACTION_STATUS: 'mixed',
        }
        param_whitelist = {
            consts.PARAM_LIMIT: 'single',
            consts.PARAM_MARKER: 'single',
            consts.PARAM_SORT: 'single',
            consts.PARAM_GLOBAL_PROJECT: 'single',
        }
        for key in req.params.keys():
            if (key not in param_whitelist.keys() and key not in
                    filter_whitelist.keys()):
                raise exc.HTTPBadRequest(_('Invalid parameter %s') % key)
        params = util.get_allowed_params(req.params, param_whitelist)
        filters = util.get_allowed_params(req.params, filter_whitelist)

        key = consts.PARAM_LIMIT
        if key in params:
            params[key] = utils.parse_int_param(key, params[key])

        key = consts.PARAM_GLOBAL_PROJECT
        if key in params:
            global_project = utils.parse_bool_param(key, params[key])
            params.pop(key)
            params['project_safe'] = not global_project

        if not filters:
            filters = None

        actions = self.rpc_client.action_list(req.context, filters=filters,
                                              **params)

        return {'actions': actions}

    @util.policy_enforce
    def create(self, req, body):
        data = ActionData(body)
        result = self.rpc_client.action_create(req.context,
                                               data.name(),
                                               data.target(),
                                               data.action(),
                                               data.params())

        return result

    @util.policy_enforce
    def get(self, req, action_id):
        action = self.rpc_client.action_get(req.context, action_id)
        if not action:
            raise exc.HTTPNotFound()

        return {'action': action}
