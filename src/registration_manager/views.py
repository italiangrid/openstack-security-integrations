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

from openstack_auth_shib.models import RSTATUS_PENDING
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

    def get_data(self):
    
        reqTable = dict()
        
        with transaction.atomic():
        
            allPrjReqs = PrjRequest.objects.all()
            
            allRegReqs = RegRequest.objects.filter(flowstatus=RSTATUS_PENDING)
            
            regid_list = [ tmpRegReq.registration.regid for tmpRegReq in allRegReqs ]
            
            for prjReq in allPrjReqs:
                
                rData = RegistrData()
                rData.username = prjReq.registration.username
                rData.fullname = prjReq.registration.givenname + " " + prjReq.registration.sn
                rData.organization = prjReq.registration.organization
                rData.phone = prjReq.registration.phone
                
                if prjReq.flowstatus == PSTATUS_RENEW_MEMB:

                    if prjReq.project.status == PRJ_GUEST:
                        rData.code = RegistrData.GUEST_RENEW
                    else:
                        rData.code = RegistrData.USR_RENEW
                    rData.project = prjReq.project.projectname
                    requestid = "%d:%s" % (prjReq.registration.regid, prjReq.project.projectname)

                elif prjReq.flowstatus == PSTATUS_RENEW_ADMIN:

                    rData.code = RegistrData.PRJADM_RENEW
                    rData.project = prjReq.project.projectname
                    requestid = "%d:%s" % (prjReq.registration.regid, prjReq.project.projectname)

                elif prjReq.project.status == PRJ_GUEST:

                    rData.code = RegistrData.NEW_USR_GUEST_PRJ
                    requestid = "%d:" % prjReq.registration.regid

                elif prjReq.project.projectid:

                    if prjReq.registration.regid in regid_list:
                        rData.code = RegistrData.NEW_USR_EX_PRJ
                        requestid = "%d:" % prjReq.registration.regid
                    else:
                        rData.code = RegistrData.EX_USR_EX_PRJ
                        rData.project = prjReq.project.projectname
                        requestid = "%d:%s" % (prjReq.registration.regid, prjReq.project.projectname)

                else:

                    if prjReq.registration.regid in regid_list:
                        rData.code = RegistrData.NEW_USR_NEW_PRJ
                        rData.project = prjReq.project.projectname
                        requestid = "%d:%s" % (prjReq.registration.regid, prjReq.project.projectname)
                    else:
                        rData.code = RegistrData.EX_USR_NEW_PRJ
                        rData.project = prjReq.project.projectname
                        requestid = "%d:%s" % (prjReq.registration.regid, prjReq.project.projectname)

                rData.requestid = requestid
                
                if not requestid in reqTable:
                    reqTable[requestid] = rData

        result = reqTable.values()
        result.sort()
        return result

class AbstractCheckView(forms.ModalFormView):

    def get_object(self):
        if not hasattr(self, "_object"):
            try:
                tmpTuple = self.kwargs['requestid'].split(':')
                regid = int(tmpTuple[0])
                
                tmplist = RegRequest.objects.filter(registration__regid=regid)
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
        return {
            'regid' : self.get_object().registration.regid,
            'username' : self.get_object().registration.username,
            'extaccount' : self.get_object().externalid,
            'expiration' : datetime.now() + timedelta(365)
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
        return { 
            'requestid' : self.kwargs['requestid'],
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

                tmpres = RegRequest.objects.filter(registration__regid=regid)
                if len(tmpres):
                    reg_item = tmpres[0].registration
                    tmpdict['extaccount'] = tmpres[0].externalid
                    tmpdict['contact'] = tmpres[0].contactper
                    tmpdict['email'] = tmpres[0].email
                    tmpdict['notes'] = tmpres[0].notes

                    for prj_req in PrjRequest.objects.filter(registration__regid=regid):
                        if prj_req.project.projectid:
                            tmpdict['memberof'].append(prj_req.project.projectname)
                        else:
                            tmpdict['newprojects'].append(prj_req.project.projectname)

                elif prjname:
                    q_args = {
                        'registration__regid' : regid,
                        'project__projectname' : prjname
                    }
                    prj_req = PrjRequest.objects.filter(**q_args)[0]
                    reg_item = prj_req.registration

                    tmpdict['notes'] = prj_req.notes
                    if prj_req.project.projectid:
                        tmpdict['memberof'].append(prjname)
                    else:
                        tmpdict['newprojects'].append(prjname)

                    tmpem = EMail.objects.filter(registration__regid=regid)
                    tmpdict['email'] = tmpem[0].email if len(tmpem) else "-"

                if reg_item:
                    tmpdict['username'] = reg_item.username
                    tmpdict['fullname'] = reg_item.givenname + " " + reg_item.sn
                    tmpdict['organization'] = reg_item.organization
                    tmpdict['phone'] = reg_item.phone

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




