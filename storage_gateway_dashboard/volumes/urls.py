# Copyright 2012 Nebula, Inc.
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

from django.conf.urls import url

from storage_gateway_dashboard.backups \
    import views as backup_views
from storage_gateway_dashboard.volumes import views

urlpatterns = [
    url(r'^$', views.VolumesView.as_view(), name='index'),
    url(r'^create/$', views.CreateView.as_view(), name='create'),
    url(r'^enable/$', views.EnableView.as_view(), name='enable'),
    url(r'^(?P<volume_id>[^/]+)/attach/$',
        views.EditAttachmentsView.as_view(),
        name='attach'),
    url(r'^(?P<volume_id>[^/]+)/create_snapshot/$',
        views.CreateSnapshotView.as_view(),
        name='create_snapshot'),
    url(r'^(?P<volume_id>[^/]+)/create_backup/$',
        backup_views.CreateBackupView.as_view(),
        name='create_backup'),
    url(r'^(?P<volume_id>[^/]+)/$',
        views.DetailView.as_view(),
        name='detail'),
    url(r'^(?P<volume_id>[^/]+)/update/$',
        views.UpdateView.as_view(),
        name='update'),
    url(r'^(?P<volume_id>[^/]+)/rollback/$',
        views.RollbackVolume.as_view(),
        name='rollback'),
]
