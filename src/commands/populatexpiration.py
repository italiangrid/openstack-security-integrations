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

from django.db import transaction
from django.core.management.base import CommandError
from openstack_auth_shib.models import Registration
from openstack_auth_shib.models import Project
from openstack_auth_shib.models import Expiration
from openstack_auth_shib.models import EMail
from openstack_auth_shib.models import PrjRole

from horizon.management.commands.cronscript_utils import CloudVenetoCommand
from horizon.management.commands.cronscript_utils import get_prjman_roleid

from keystoneclient.v3 import client

LOG = logging.getLogger("populatexpiration")

class Command(CloudVenetoCommand):

    def handle(self, *args, **options):

        super(Command, self).handle(options)

        try:

            prj_dict = dict()
            
            for prj_item in Project.objects.all():
                if prj_item.projectid:
                    prj_dict[prj_item.projectid] = prj_item

            #
            # TODO define the user_domain_name and project_domain_name
            #
            keystone_client = client.Client(username=self.config.cron_user,
                                            password=self.config.cron_pwd,
                                            project_name=self.config.cron_prj,
                                            cacert=self.config.cron_ca,
                                            user_domain_name=self.config.cron_domain,
                                            project_domain_name=self.config.cron_domain,
                                            auth_url=self.config.cron_kurl)

            LOG.info("Populating the expiration table")

            with transaction.atomic():
                for reg_user in Registration.objects.all():
                
                    if not reg_user.userid:
                        LOG.info("Skipped unregistered user %s" % reg_user.username)
                        continue
                    
                    for r_item in keystone_client.role_assignments.list(user=reg_user.userid):
                        if not r_item.scope['project']['id'] in prj_dict:
                            LOG.info("Skipped unregistered project %s for %s" % \
                            (r_item.scope['project']['id'], reg_user.username))
                        curr_prj = prj_dict[r_item.scope['project']['id']]
                        
                        if Expiration.objects.filter(
                            registration=reg_user,
                            project=curr_prj
                        ).count() > 0:
                            continue

                        prj_exp = Expiration()
                        prj_exp.registration = reg_user
                        prj_exp.project = curr_prj
                        prj_exp.expdate = reg_user.expdate
                        prj_exp.save()
                        
                        LOG.info("Imported expiration for %s in %s: %s" % \
                        (reg_user.username, curr_prj.projectname, \
                        reg_user.expdate.strftime("%A, %d. %B %Y %I:%M%p")))

            LOG.info("Populating the email table")

            with transaction.atomic():
                for reg_user in Registration.objects.all():

                    if not reg_user.userid:
                        LOG.info("Skipped unregistered user %s" % reg_user.username)
                        continue

                    tmpres = keystone_client.users.get(reg_user.userid)
                    if not tmpres:
                        continue

                    if EMail.objects.filter(registration=reg_user).count() > 0:
                        continue

                    mail_obj = EMail()
                    mail_obj.registration = reg_user
                    mail_obj.email = tmpres.email
                    mail_obj.save()

                    LOG.info("Imported email for %s: %s" % (reg_user.username, tmpres.email))

            LOG.info("Populating the project roles table")

            tnt_admin_roleid = get_prjman_roleid(keystone_client)

            with transaction.atomic():

                PrjRole.objects.all().delete()

                prj_dict = dict()
                for prj_obj in Project.objects.all():
                    prj_dict[prj_obj.projectid] = prj_obj

                for reg_user in Registration.objects.all():

                    if not reg_user.userid:
                        LOG.info("Skipped unregistered user %s" % reg_user.username)
                        continue

                    for role_obj in keystone_client.role_assignments.list(reg_user.userid):
                        if role_obj.role['id'] == tnt_admin_roleid:
                            tmpprjid = role_obj.scope['project']['id']
                            prjRole = PrjRole()
                            prjRole.registration = reg_user
                            prjRole.project = prj_dict[tmpprjid]
                            prjRole.roleid = role_obj.role['id']
                            prjRole.save()

                            LOG.info("Imported admin %s for %s" % (reg_user.username, 
                                     prj_dict[tmpprjid].projectname))

        except:
            LOG.error("Import failed", exc_info=True)
            raise CommandError("Import failed")

