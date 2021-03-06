#  Copyright (c) 2014 INFN - "Istituto Nazionale di Fisica Nucleare" - Italy
#  All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License. 


import logging
import base64
import json

from Crypto.Cipher import AES
from Crypto import __version__ as crypto_version
if crypto_version.startswith('2.0'):
    from Crypto.Util import randpool
else:
    from Crypto import Random

from django.conf import settings
from django.utils.translation import ugettext as _

from keystoneclient.exceptions import AuthorizationFailure
from keystoneclient.exceptions import Unauthorized
from keystoneclient.exceptions import NotFound
from keystoneclient.exceptions import ClientException
from keystoneclient.v3.client import Client as BaseClient

from openstack_auth import backend as base_backend
from openstack_auth.exceptions import KeystoneAuthException
from openstack_auth.user import create_user_from_token
from openstack_auth.user import Token
from openstack_auth.utils import get_keystone_version


LOG = logging.getLogger(__name__)


class ExtClient(BaseClient):

    def __init__(self, **kwargs):
        if 'secret_token' in kwargs:
            self.secret_token = kwargs['secret_token']
            del kwargs['secret_token']
        else:
            self.secret_token = None
        super(ExtClient, self).__init__(**kwargs)

    def get_raw_token_from_identity_service(self, auth_url, user_id=None,
                                            username=None,
                                            user_domain_id=None,
                                            user_domain_name=None,
                                            password=None,
                                            domain_id=None, domain_name=None,
                                            project_id=None, project_name=None,
                                            project_domain_id=None,
                                            project_domain_name=None,
                                            token=None,
                                            trust_id=None,
                                            **kwargs):

        if self.secret_token == None:
            return super(ExtClient, self).get_raw_token_from_identity_service(
                                                   auth_url, user_id, username,
                                                   user_domain_id, user_domain_name,
                                                   password, domain_id, domain_name,
                                                   project_id, project_name,
                                                   project_domain_id,
                                                   project_domain_name, token,
                                                   trust_id)
        try:
        
            headers = {}
            if auth_url is None:
                raise AuthorizationFailure("Cannot authenticate without a valid auth_url")
            url = auth_url + "/auth/tokens"
            body = {'auth': {'identity': {}}}
            ident = body['auth']['identity']
        
            ident['methods'] = ['sKey']
            ident['sKey'] = { 'token' : self.secret_token }
        

            resp, body = self.request(url, 'POST', body=body, headers=headers)
            return resp, body
            
        except (AuthorizationFailure, Unauthorized, NotFound):
            LOG.debug('Authorization failed.')
            raise
        except Exception as e:
            raise AuthorizationFailure('Authorization failed: %s' % e)
            




def create_cryptoken(aes_key, data):

    if len(aes_key) >= 32:
        aes_key = aes_key[:32]
    elif len(aes_key) >= 16:
        aes_key = aes_key[:16]
    elif len(aes_key) >= 8:
        aes_key = aes_key[:8]
    else:
        raise AuthorizationFailure()
    
    if crypto_version.startswith('2.0'):
    
        prng = randpool.RandomPool()
        iv = prng.get_bytes(256)
        cipher = AES.new(aes_key, AES.MODE_CFB)
        tmpbuf = cipher.encrypt(iv)
        tmpbuf += cipher.encrypt(data)
        return base64.b64encode(tmpbuf)
    
    else:
        
        prng = Random.new()
        iv = prng.read(16)
        cipher = AES.new(aes_key, AES.MODE_CFB, iv)
        return base64.b64encode(iv + cipher.encrypt(data))

################################################################################################
# Register this backend in /etc/openstack-dashboard/local_settings
# AUTHENTICATION_BACKENDS = ('openstack_auth_shib.backend.ExtKeystoneBackend',)
################################################################################################
class ExtKeystoneBackend(base_backend.KeystoneBackend):

    def authenticate(self, **kwargs):

        auth_url = kwargs.get('auth_url', None)
        request = kwargs.get('request', None)
        username = kwargs.get('username', None)
        password = kwargs.get('password', None)
        user_domain_name = kwargs.get('user_domain_name', None)
        
        if password:
            parentObj = super(ExtKeystoneBackend, self)
            return parentObj.authenticate(**kwargs)

        LOG.debug('Authenticating user "%s".' % username)

        insecure = getattr(settings, 'OPENSTACK_SSL_NO_VERIFY', False)
        cacert = getattr(settings, 'OPENSTACK_SSL_CACERT', None)
        ep_type = getattr(settings, 'OPENSTACK_ENDPOINT_TYPE', 'publicURL')
        secret_key = getattr(settings, 'KEYSTONE_SECRET_KEY', None)
        
        fqun = json.dumps({
            'username' : username,
            'domain' : user_domain_name
        })

        try:
        
            secret_token = create_cryptoken(secret_key, fqun)
            
            client = ExtClient(user_domain_name=user_domain_name,
                               username=username,
                               secret_token=secret_token,
                               auth_url=auth_url,
                               insecure=insecure,
                               cacert=cacert,
                               debug=settings.DEBUG)

            unscoped_auth_ref = client.auth_ref
            unscoped_token = Token(auth_ref=unscoped_auth_ref)
            
            # Force API V3
            if get_keystone_version() < 3:
                unscoped_token.serviceCatalog = unscoped_auth_ref.get('catalog', [])
                unscoped_token.roles = unscoped_auth_ref.get('roles', [])
            
        except ClientException as exc:
            LOG.debug(exc.message, exc_info=True)
            raise
        except Exception as exc:
            msg = _("An error occurred authenticating. Please try again later.")
            LOG.debug(exc.message, exc_info=True)
            raise KeystoneAuthException(msg)

        self.check_auth_expiry(unscoped_auth_ref)

        if unscoped_auth_ref.project_scoped:
            auth_ref = unscoped_auth_ref
        else:
            # For now we list all the user's projects and iterate through.
            try:
                client.management_url = auth_url
                projects = client.projects.list(user=unscoped_auth_ref.user_id)
            except (ClientException, AuthorizationFailure) as exc:
                msg = _('Unable to retrieve authorized projects.')
                raise KeystoneAuthException(msg)

            # Abort if there are no projects for this user
            if not projects:
                msg = _('You are not authorized for any projects.')
                raise KeystoneAuthException(msg)

            while projects:
                project = projects.pop()
                try:
                    client = BaseClient(
                        tenant_id=project.id,
                        token=unscoped_auth_ref.auth_token,
                        auth_url=auth_url,
                        insecure=insecure,
                        debug=settings.DEBUG)
                    auth_ref = client.auth_ref
                    break
                except (ClientException, AuthorizationFailure):
                    auth_ref = None

            if auth_ref is None:
                msg = _("Unable to authenticate to any available projects.")
                raise KeystoneAuthException(msg)

            # Check expiry for our new scoped token.
            self.check_auth_expiry(auth_ref)

        # If we made it here we succeeded. Create our User!
        
        # Force API V3
        project_token = Token(auth_ref)
        if get_keystone_version() < 3:
            project_token.serviceCatalog = auth_ref.get('catalog', [])
            project_token.roles = auth_ref.get('roles', [])
        
        user = create_user_from_token(request,
                                      project_token,
                                      client.service_catalog.url_for(endpoint_type=ep_type))

        if request is not None:
            request.session['unscoped_token'] = unscoped_token.id
            request.user = user

            # Support client caching to save on auth calls.
            setattr(request, base_backend.KEYSTONE_CLIENT_ATTR, client)

        LOG.debug('Authentication completed for user "%s".' % username)
        return user



################################################################################################
#  Authentication plugin
################################################################################################

from openstack_auth.plugin import base as base_plugin
from keystoneclient.auth.identity.base import BaseIdentityPlugin

__all__ = ['SKeyPluginFactory']

class SKeyPlugin(BaseIdentityPlugin):

    def __init__(self, auth_url=None, **kwargs):
        self.auth_url = auth_url
        self.request = kwargs.get('request', None)
        self.username = kwargs.get('username', None)
        self.user_domain_name = kwargs.get('user_domain_name', None)
        
        super(SKeyPlugin, self).__init__(auth_url=self.auth_url,
                                         username=self.username)
        LOG.debug('SkeyPlugin initialized')
            
    def get_auth_ref(self, session, **kwargs):
        LOG.debug('Authenticating user "%s".' % self.username)

        insecure = getattr(settings, 'OPENSTACK_SSL_NO_VERIFY', False)
        cacert = getattr(settings, 'OPENSTACK_SSL_CACERT', None)
        ep_type = getattr(settings, 'OPENSTACK_ENDPOINT_TYPE', 'publicURL')
        secret_key = getattr(settings, 'KEYSTONE_SECRET_KEY', None)
        
        fqun = json.dumps({
            'username' : self.username,
            'domain' : self.user_domain_name
        })

        try:
        
            secret_token = create_cryptoken(secret_key, fqun)
            
            client = ExtClient(user_domain_name=self.user_domain_name,
                               username=self.username,
                               secret_token=secret_token,
                               auth_url=self.auth_url,
                               insecure=insecure,
                               cacert=cacert,
                               debug=settings.DEBUG)

            unscoped_auth_ref = client.auth_ref
            LOG.debug('User %s authenticated' % self.username)
            return unscoped_auth_ref
            
        except ClientException as exc:
            LOG.debug(exc.message, exc_info=True)
            raise
        except Exception as exc:
            msg = _("An error occurred authenticating. Please try again later.")
            LOG.debug(exc.message, exc_info=True)
            raise KeystoneAuthException(msg)
        

class SKeyPluginFactory(base_plugin.BasePlugin):

    def get_plugin(self, auth_url=None, **kwargs):
        password = kwargs.get('password', None)
        if password:
            return None
        
        return SKeyPlugin(auth_url, **kwargs)


