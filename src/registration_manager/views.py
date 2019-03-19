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
from datetime import datetime, timedelta

from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse_lazy
from django.db import transaction

from horizon import tables
from horizon import exceptions
from horizon import forms

from openstack_auth_shib.models import RegRequest
from openstack_auth_shib.models import PrjRequest
from openstack_auth_shib.models import EMail
from openstack_auth_shib.models import PrjRole

from openstack_auth_shib.models import RSTATUS_PENDING
from openstack_auth_shib.models import RSTATUS_REMINDER
from openstack_auth_shib.models import PRJ_PRIVATE
from openstack_auth_shib.models import PRJ_GUEST
from openstack_auth_shib.models import PSTATUS_RENEW_ADMIN
from openstack_auth_shib.models import PSTATUS_RENEW_MEMB

from .tables import RegistrData
from .tables import OperationTable
from .forms import PreCheckForm
from .forms import GrantAllForm
from .forms import RejectForm
from .forms import ForcedCheckForm
from .forms import ForcedRejectForm
from .forms import NewProjectCheckForm
from .forms import NewProjectRejectForm
from .forms import GuestCheckForm
from .forms import RenewAdminForm
from .forms import DetailsForm

LOG = logging.getLogger(__name__)

class MainView(tables.DataTableView):
    table_class = OperationTable
    template_name = 'idmanager/registration_manager/reg_manager.html'
    page_title = _("Registrations")

    def _initRegistrData(self, registration):
        rData = RegistrData()
        rData.username = registration.username
        rData.fullname = registration.givenname + " " + registration.sn
        rData.organization = registration.organization
        rData.phone = registration.phone
        return rData

    def get_data(self):
    
        reqTable = dict()
        remTable = dict()
        
        with transaction.atomic():
        
            regid_pending = set()
            for tmpRegReq in RegRequest.objects.filter(flowstatus=RSTATUS_PENDING):
                regid_pending.add(tmpRegReq.registration.regid)

            for tmpRegReq in RegRequest.objects.filter(flowstatus=RSTATUS_REMINDER):
                rData = self._initRegistrData(tmpRegReq.registration)
                rData.requestid = "%d:" % tmpRegReq.registration.regid
                rData.code = RegistrData.REMINDER
                remTable[tmpRegReq.registration.regid] = rData

            for prjReq in PrjRequest.objects.all():
                
                rData = self._initRegistrData(prjReq.registration)
                curr_regid = prjReq.registration.regid
                
                if prjReq.flowstatus == PSTATUS_RENEW_MEMB:

                    if prjReq.project.status == PRJ_GUEST:
                        rData.code = RegistrData.GUEST_RENEW
                    else:
                        rData.code = RegistrData.USR_RENEW
                    rData.project = prjReq.project.projectname
                    rData.notes = prjReq.notes
                    requestid = "%d:%s" % (curr_regid, prjReq.project.projectname)

                elif prjReq.flowstatus == PSTATUS_RENEW_ADMIN:

                    rData.code = RegistrData.PRJADM_RENEW
                    rData.project = prjReq.project.projectname
                    rData.notes = prjReq.notes
                    requestid = "%d:%s" % (curr_regid, prjReq.project.projectname)

                elif prjReq.project.status == PRJ_GUEST:

                    rData.code = RegistrData.NEW_USR_GUEST_PRJ
                    requestid = "%d:" % curr_regid
                    if curr_regid in remTable:
                        del remTable[curr_regid]

                elif prjReq.project.projectid:

                    if curr_regid in regid_pending:
                        rData.code = RegistrData.NEW_USR_EX_PRJ
                        requestid = "%d:" % curr_regid
                    else:
                        rData.code = RegistrData.EX_USR_EX_PRJ
                        rData.project = prjReq.project.projectname
                        requestid = "%d:%s" % (curr_regid, prjReq.project.projectname)

                    if curr_regid in remTable:
                        del remTable[curr_regid]

                else:

                    if curr_regid in regid_pending:
                        rData.code = RegistrData.NEW_USR_NEW_PRJ
                    else:
                        rData.code = RegistrData.EX_USR_NEW_PRJ
                    rData.project = prjReq.project.projectname
                    requestid = "%d:%s" % (curr_regid, prjReq.project.projectname)
                    if prjReq.project.status == PRJ_PRIVATE:
                        rData.project += " (%s)" % _("Private")

                    if curr_regid in remTable:
                        del remTable[curr_regid]

                rData.requestid = requestid
                
                if not requestid in reqTable:
                    reqTable[requestid] = rData

        result = reqTable.values() + remTable.values()
        result.sort()
        return result

class AbstractCheckView(forms.ModalFormView):

    def get_object(self):
        if not hasattr(self, "_object"):
            try:
                tmpTuple = self.kwargs['requestid'].split(':')
                regid = int(tmpTuple[0])
                
                tmplist = RegRequest.objects.filter(registration__regid=regid, flowstatus=RSTATUS_PENDING)
                if len(tmplist):
                    self._object = tmplist[0]
                else:
                    raise Exception("Database error")
                    
            except Exception:
                LOG.error("Registration error", exc_info=True)
                redirect = reverse_lazy("horizon:idmanager:registration_manager:index")
                exceptions.handle(self.request, _('Unable to pre-check request.'), redirect=redirect)

        return self._object

    def get_context_data(self, **kwargs):
        context = super(AbstractCheckView, self).get_context_data(**kwargs)
        context['requestid'] = "%d:" % self.get_object().registration.regid
        context['extaccount'] = self.get_object().externalid
        context['contact'] = self.get_object().contactper
        context['organization'] = self.get_object().registration.organization
        context['email'] = self.get_object().email
        return context

class PreCheckView(AbstractCheckView):
    form_class = PreCheckForm
    template_name = 'idmanager/registration_manager/precheck.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_initial(self):
        return {
            'regid' : self.get_object().registration.regid,
            'username' : self.get_object().registration.username,
            'extaccount' : self.get_object().externalid
        }

class GrantAllView(AbstractCheckView):
    form_class = GrantAllForm
    template_name = 'idmanager/registration_manager/precheck.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_context_data(self, **kwargs):
        context = super(GrantAllView, self).get_context_data(**kwargs)
        context['grantallmode'] = True
        return context

    def get_initial(self):

        oldpname, oldpdescr = get_project_details(self.kwargs.get('requestid', ''))

        return {
            'regid' : self.get_object().registration.regid,
            'username' : self.get_object().registration.username,
            'extaccount' : self.get_object().externalid,
            'expiration' : datetime.now() + timedelta(365),
            'rename' : oldpname if oldpname else '' ,
            'newdescr' : oldpdescr if oldpdescr else ''
        }

class RejectView(AbstractCheckView):
    form_class = RejectForm
    template_name = 'idmanager/registration_manager/reject.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_initial(self):
        return {
            'regid' : self.get_object().registration.regid
        }

class ForcedApproveView(forms.ModalFormView):
    form_class = ForcedCheckForm
    template_name = 'idmanager/registration_manager/forced.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = self.kwargs['requestid']
        return self._object

    def get_context_data(self, **kwargs):
        context = super(ForcedApproveView, self).get_context_data(**kwargs)
        context['requestid'] = self.kwargs['requestid']
        context['action'] = 'accept'
        return context
        
    def get_initial(self):
        return { 
            'requestid' : self.kwargs['requestid'],
            'expiration' : datetime.now() + timedelta(365)
        }

class ForcedRejectView(forms.ModalFormView):
    form_class = ForcedRejectForm
    template_name = 'idmanager/registration_manager/forced.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = self.kwargs['requestid']
        return self._object

    def get_context_data(self, **kwargs):
        context = super(ForcedRejectView, self).get_context_data(**kwargs)
        context['requestid'] = self.kwargs['requestid']
        context['action'] = 'reject'
        return context
        
    def get_initial(self):
        return { 
            'requestid' : self.kwargs['requestid']
        }

class NewProjectView(forms.ModalFormView):
    form_class = NewProjectCheckForm
    template_name = 'idmanager/registration_manager/newproject.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')
    
    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = self.kwargs['requestid']
        return self._object

    def get_context_data(self, **kwargs):
        context = super(NewProjectView, self).get_context_data(**kwargs)
        context['requestid'] = self.kwargs['requestid']
        context['action'] = 'accept'
        return context
        
    def get_initial(self):

        oldpname, oldpdescr = get_project_details(self.kwargs['requestid'])

        return { 
            'requestid' : self.kwargs['requestid'],
            'newname' : oldpname if oldpname else '',
            'newdescr' : oldpdescr if oldpdescr else '',
            'expiration' : datetime.now() + timedelta(365)
        }

class RejectProjectView(forms.ModalFormView):
    form_class = NewProjectRejectForm
    template_name = 'idmanager/registration_manager/newproject.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')
    
    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = self.kwargs['requestid']
        return self._object

    def get_context_data(self, **kwargs):
        context = super(RejectProjectView, self).get_context_data(**kwargs)
        context['requestid'] = self.kwargs['requestid']
        context['action'] = 'reject'
        return context
        
    def get_initial(self):
        return { 
            'requestid' : self.kwargs['requestid']
        }

class GuestApproveView(AbstractCheckView):
    form_class = GuestCheckForm
    template_name = 'idmanager/registration_manager/precheck.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')
    
    def get_context_data(self, **kwargs):
        context = super(GuestApproveView, self).get_context_data(**kwargs)
        context['guestmode'] = True
        return context

    def get_initial(self):
        return {
            'regid' : self.get_object().registration.regid,
            'username' : self.get_object().registration.username,
            'expiration' : datetime.now() + timedelta(365)
        }

class RenewAdminView(forms.ModalFormView):
    form_class = RenewAdminForm
    template_name = 'idmanager/registration_manager/renewadmin.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = self.kwargs['requestid']
        return self._object

    def get_context_data(self, **kwargs):
        context = super(RenewAdminView, self).get_context_data(**kwargs)
        context['requestid'] = self.kwargs['requestid']
        context['action'] = 'accept'
        context['is_admin'] = True
        return context
        
    def get_initial(self):
        return { 
            'requestid' : self.kwargs['requestid'],
            'expiration' : datetime.now() + timedelta(365)
        }

class ForcedRenewView(RenewAdminView):
    form_class = RenewAdminForm
    template_name = 'idmanager/registration_manager/renewadmin.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_context_data(self, **kwargs):
        context = super(ForcedRenewView, self).get_context_data(**kwargs)
        context['is_admin'] = False
        return context

class DetailsView(forms.ModalFormView):
    form_class = DetailsForm
    template_name = 'idmanager/registration_manager/details.html'
    success_url = reverse_lazy('horizon:idmanager:registration_manager:index')

    def get_object(self):
        if not hasattr(self, "_object"):
            try:
                tmpTuple = self.kwargs['requestid'].split(':')
                regid = int(tmpTuple[0])
                prjname = tmpTuple[1] if len(tmpTuple) > 1 else None

                tmpdict = dict()
                tmpdict['requestid'] = self.kwargs['requestid']
                tmpdict['regid'] = regid
                tmpdict['newprojects'] = list()
                tmpdict['memberof'] = list()
                reg_item = None
                prj_list = list()

                tmpres = RegRequest.objects.filter(registration__regid=regid)
                if len(tmpres):
                    reg_item = tmpres[0].registration
                    tmpdict['extaccount'] = tmpres[0].externalid
                    tmpdict['contact'] = tmpres[0].contactper
                    tmpdict['email'] = tmpres[0].email
                    tmpdict['notes'] = tmpres[0].notes

                    if tmpres[0].flowstatus == RSTATUS_PENDING:
                        for x in PrjRequest.objects.filter(registration__regid=regid):
                            prj_list.append(x.project)
                    else:
                        for x in PrjRole.objects.filter(registration__regid=regid):
                            prj_list.append(x.project)

                elif prjname:
                    q_args = {
                        'registration__regid' : regid,
                        'project__projectname' : prjname
                    }
                    prj_req = PrjRequest.objects.filter(**q_args)[0]
                    reg_item = prj_req.registration
                    prj_list.append(prj_req.project)

                    tmpem = EMail.objects.filter(registration__regid=regid)
                    tmpdict['email'] = tmpem[0].email if len(tmpem) else "-"
                    tmpdict['notes'] = prj_req.notes

                if reg_item:
                    tmpdict['username'] = reg_item.username
                    tmpdict['fullname'] = reg_item.givenname + " " + reg_item.sn
                    tmpdict['organization'] = reg_item.organization
                    tmpdict['phone'] = reg_item.phone

                for prj_item in prj_list:
                    if prj_item.projectid:
                        tmpdict['memberof'].append(prj_item.projectname)
                    else:
                        is_priv = prj_item.status == PRJ_PRIVATE
                        tmpdict['newprojects'].append((prj_item.projectname, is_priv))

                self._object = tmpdict

            except Exception:
                LOG.error("Registration error", exc_info=True)
                redirect = reverse_lazy("horizon:idmanager:registration_manager:index")
                exceptions.handle(self.request, _('Unable to retrieve details.'), redirect=redirect)

        return self._object

    def get_initial(self):
        return { 'requestid' : self.kwargs['requestid'] }

    def get_context_data(self, **kwargs):
        context = super(DetailsView, self).get_context_data(**kwargs)
        context.update(self.get_object())
        return context

def get_project_details(requestid):

    tmpt = requestid.split(':')

    if len(tmpt) == 2:
        try:
            prj_req = PrjRequest.objects.filter(
                registration__regid = int(tmpt[0]),
                project__projectname = tmpt[1]
            )[0]
            return (prj_req.project.projectname, prj_req.project.description)
        except Exception:
            LOG.error("Registration error", exc_info=True)

    return (None, None)



