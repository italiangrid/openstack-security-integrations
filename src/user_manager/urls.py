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


from django import VERSION as django_version
from django.conf.urls import url
from openstack_dashboard.dashboards.idmanager.user_manager import views

index_url = url(r'^$', views.IndexView.as_view(), name='index')
chkorp_url = url(r'^checkorphans/$', views.CheckOrphansView.as_view(), name='checkorphans')
mod_url = url(r'^(?P<user_id>[^/]+)/update/$', views.UpdateView.as_view(), name='update')
ren_url = url(r'^(?P<user_id>[^/]+)/renew/$', views.RenewView.as_view(), name='renew')
react_url = url(r'^(?P<user_id>[^/]+)/reactivate/$', views.ReactivateView.as_view(),
                name='reactivate')
modpwd_url = url(r'^(?P<user_id>[^/]+)/change_password/$', views.ChangePasswordView.as_view(),
                 name='change_password')
detail_url = url(r'^(?P<user_id>[^/]+)/detail/$', views.DetailView.as_view(), name='detail')

if django_version[1] < 11:

    from django.conf.urls import patterns

    urlpatterns = patterns('openstack_dashboard.dashboards.idmanager.user_manager.views',
                           index_url,
                           chkorp_url,
                           mod_url,
                           ren_url,
                           react_url,
                           modpwd_url,
                           detail_url
    )

else:

    urlpatterns = [
        index_url,
        chkorp_url,
        mod_url,
        ren_url,
        react_url,
        modpwd_url,
        detail_url
    ]

