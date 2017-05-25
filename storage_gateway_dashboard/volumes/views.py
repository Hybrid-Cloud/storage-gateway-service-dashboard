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

"""
Views for managing volumes.
"""

from collections import OrderedDict
import json

from django.core.urlresolvers import reverse
from django.core.urlresolvers import reverse_lazy
from django.utils import encoding
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import tables
from horizon import tabs
from horizon.utils import memoized

from openstack_dashboard.api import cinder
from openstack_dashboard.api import nova
from openstack_dashboard import exceptions as dashboard_exception
from openstack_dashboard.usage import quotas
from openstack_dashboard.utils import filters

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.common import table as common_table
from storage_gateway_dashboard.volumes import forms as volume_forms
from storage_gateway_dashboard.volumes import tables as volume_tables
from storage_gateway_dashboard.volumes import tabs as volume_tabs


class VolumeTableMixIn(object):
    _has_more_data = False
    _has_prev_data = False

    def _get_volumes(self, search_opts=None):
        try:
            marker, sort_dir = self._get_marker()
            volumes, self._has_more_data, self._has_prev_data = \
                sg_api.volume_list_paged(self.request, marker=marker,
                                         search_opts=search_opts,
                                         sort_dir=sort_dir, paginate=True)

            if sort_dir == "asc":
                volumes.reverse()

            return volumes
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve volume list.'))
            return []

    def _get_instances(self, search_opts=None, instance_ids=None):
        if not instance_ids:
            return []
        try:
            # TODO(tsufiev): we should pass attached_instance_ids to
            # nova.server_list as soon as Nova API allows for this
            instances, has_more = nova.server_list(self.request,
                                                   search_opts=search_opts)
            return instances
        except Exception:
            exceptions.handle(self.request,
                              _("Unable to retrieve volume/instance "
                                "attachment information"))
            return []

    def _get_volumes_ids_with_snapshots(self, search_opts=None):
        try:
            volume_ids = []
            snapshots = sg_api.volume_snapshot_list(
                self.request, search_opts=search_opts)
            if snapshots:
                # extract out the volume ids
                volume_ids = set([(s.volume_id) for s in snapshots])
        except Exception:
            exceptions.handle(self.request,
                              _("Unable to retrieve snapshot list."))

        return volume_ids

    def _get_attached_instance_ids(self, volumes):
        attached_instance_ids = []
        for volume in volumes:
            for att in volume.attachments:
                server_id = att.get('server_id', None)
                if server_id is not None:
                    attached_instance_ids.append(server_id)
        return attached_instance_ids

    # set attachment string and if volume has snapshots
    def _set_volume_attributes(self,
                               volumes,
                               instances,
                               volume_ids_with_snapshots):
        instances = OrderedDict([(inst.id, inst) for inst in instances])
        for volume in volumes:
            if volume_ids_with_snapshots:
                if volume.id in volume_ids_with_snapshots:
                    setattr(volume, 'has_snapshot', True)
            if instances:
                for att in volume.attachments:
                    server_id = att.get('server_id', None)
                    att['instance'] = instances.get(server_id, None)


class VolumesView(common_table.PagedTableMixin, VolumeTableMixIn,
                  tables.DataTableView):
    table_class = volume_tables.VolumesTable
    page_title = _("Storage Gateway Volumes")

    def get_data(self):
        volumes = self._get_volumes()
        attached_instance_ids = self._get_attached_instance_ids(volumes)
        instances = self._get_instances(instance_ids=attached_instance_ids)
        volume_ids_with_snapshots = self._get_volumes_ids_with_snapshots()
        self._set_volume_attributes(
            volumes, instances, volume_ids_with_snapshots)
        return volumes


class DetailView(tabs.TabView):
    tab_group_class = volume_tabs.VolumeDetailTabs
    template_name = 'horizon/common/_detail.html'
    page_title = "{{ volume.name|default:volume.id }}"

    def get_context_data(self, **kwargs):
        context = super(DetailView, self).get_context_data(**kwargs)
        volume = self.get_data()
        table = volume_tables.VolumesTable(self.request)
        context["volume"] = volume
        context["url"] = self.get_redirect_url()
        context["actions"] = table.render_row_actions(volume)
        choices = volume_tables.VolumesTableBase.STATUS_DISPLAY_CHOICES
        volume.status_label = filters.get_display_label(choices, volume.status)
        return context

    @memoized.memoized_method
    def get_data(self):
        try:
            volume_id = self.kwargs['volume_id']
            volume = sg_api.volume_get(self.request, volume_id)
        except Exception:
            redirect = self.get_redirect_url()
            exceptions.handle(self.request,
                              _('Unable to retrieve volume details.'),
                              redirect=redirect)
        return volume

    def get_redirect_url(self):
        return reverse('horizon:storage-gateway:volumes:index')

    def get_tabs(self, request, *args, **kwargs):
        volume = self.get_data()
        return self.tab_group_class(request, volume=volume, **kwargs)


class EnableView(forms.ModalFormView):
    form_class = volume_forms.EnableForm
    template_name = 'volumes/enable.html'
    submit_label = _("Enable Volume")
    submit_url = reverse_lazy("horizon:storage-gateway:volumes:enable")
    success_url = reverse_lazy('horizon:storage-gateway:volumes:index')
    page_title = _("Enable Storage Gateway Volume")

    def get_initial(self):
        initial = super(EnableView, self).get_initial()
        return initial

    def get_context_data(self, **kwargs):
        context = super(EnableView, self).get_context_data(**kwargs)
        return context


class CreateSnapshotView(forms.ModalFormView):
    form_class = volume_forms.CreateSnapshotForm
    template_name = 'volumes/create_snapshot.html'
    submit_url = "horizon:storage-gateway:volumes:create_snapshot"
    success_url = reverse_lazy('horizon:storage-gateway:snapshots:index')
    page_title = _("Create Volume Snapshot")

    def get_context_data(self, **kwargs):
        context = super(CreateSnapshotView, self).get_context_data(**kwargs)
        context['volume_id'] = self.kwargs['volume_id']
        args = (self.kwargs['volume_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        try:
            volume = sg_api.volume_get(self.request, context['volume_id'])
            if (volume.status == 'in-use'):
                context['attached'] = True
                context['form'].set_warning(_("This volume is currently "
                                              "attached to an instance. "
                                              "In some cases, creating a "
                                              "snapshot from an attached "
                                              "volume can result in a "
                                              "corrupted snapshot."))
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve volume information.'))
        return context

    def get_initial(self):
        return {'volume_id': self.kwargs["volume_id"]}


class CreateView(forms.ModalFormView):
    form_class = volume_forms.CreateForm
    template_name = 'volumes/create.html'
    submit_label = _("Create Volume")
    submit_url = reverse_lazy("horizon:storage-gateway:volumes:create")
    success_url = reverse_lazy('horizon:storage-gateway:volumes:index')
    page_title = _("Create Volume")

    def get_initial(self):
        initial = super(CreateView, self).get_initial()
        self.default_vol_type = None
        try:
            self.default_vol_type = cinder.volume_type_default(self.request)
            initial['type'] = self.default_vol_type.name
        except dashboard_exception.NOT_FOUND:
            pass
        return initial

    def get_context_data(self, **kwargs):
        context = super(CreateView, self).get_context_data(**kwargs)
        try:
            context['usages'] = quotas.tenant_limit_usages(self.request)
            context['volume_types'] = self._get_volume_types()
        except Exception:
            exceptions.handle(self.request)
        return context

    def _get_volume_types(self):
        volume_types = []
        try:
            volume_types = cinder.volume_type_list(self.request)
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve volume type list.'))

        # check if we have default volume type so we can present the
        # description of no volume type differently
        no_type_description = None
        if self.default_vol_type is None:
            message = \
                _("If \"No volume type\" is selected, the volume will be "
                  "created without a volume type.")

            no_type_description = encoding.force_text(message)

        type_descriptions = [{'name': '',
                              'description': no_type_description}] + \
                            [{'name': type.name,
                              'description': getattr(type, "description", "")}
                             for type in volume_types]

        return json.dumps(type_descriptions)


class UpdateView(forms.ModalFormView):
    form_class = volume_forms.UpdateForm
    modal_id = "update_volume_modal"
    template_name = 'volumes/update.html'
    submit_url = "horizon:storage-gateway:volumes:update"
    success_url = reverse_lazy("horizon:storage-gateway:volumes:index")
    page_title = _("Edit Volume")

    def get_object(self):
        if not hasattr(self, "_object"):
            vol_id = self.kwargs['volume_id']
            try:
                self._object = sg_api.volume_get(self.request, vol_id)
            except Exception:
                msg = _('Unable to retrieve volume.')
                url = reverse('horizon:storage-gateway:volumes:index')
                exceptions.handle(self.request, msg, redirect=url)
        return self._object

    def get_context_data(self, **kwargs):
        context = super(UpdateView, self).get_context_data(**kwargs)
        context['volume'] = self.get_object()
        args = (self.kwargs['volume_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        return context

    def get_initial(self):
        volume = self.get_object()
        return {'volume_id': self.kwargs["volume_id"],
                'name': volume.name,
                'description': volume.description}


class EditAttachmentsView(tables.DataTableView, forms.ModalFormView):
    table_class = volume_tables.AttachmentsTable
    form_class = volume_forms.AttachForm
    form_id = "attach_volume_form"
    modal_id = "attach_volume_modal"
    template_name = 'volumes/attach.html'
    submit_url = "horizon:storage-gateway:volumes:attach"
    success_url = reverse_lazy("horizon:storage-gateway:volumes:index")
    page_title = _("Manage Volume Attachments")

    @memoized.memoized_method
    def get_object(self):
        volume_id = self.kwargs['volume_id']
        try:
            return sg_api.volume_get(self.request, volume_id)
        except Exception:
            self._object = None
            exceptions.handle(self.request,
                              _('Unable to retrieve volume information.'))

    def get_data(self):
        attachments = []
        volume = self.get_object()
        if volume is not None:
            for att in volume.attachments:
                att['volume_name'] = getattr(volume, 'name', att['device'])
                attachments.append(att)
        return attachments

    def get_initial(self):
        try:
            instances, has_more = nova.server_list(self.request)
        except Exception:
            instances = []
            exceptions.handle(self.request,
                              _("Unable to retrieve attachment information."))
        return {'volume': self.get_object(),
                'instances': instances}

    @memoized.memoized_method
    def get_form(self, **kwargs):
        form_class = kwargs.get('form_class', self.get_form_class())
        return super(EditAttachmentsView, self).get_form(form_class)

    def get_context_data(self, **kwargs):
        context = super(EditAttachmentsView, self).get_context_data(**kwargs)
        context['form'] = self.get_form()
        volume = self.get_object()
        args = (self.kwargs['volume_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        if volume and volume.status == 'enabled':
            context['show_attach'] = True
        else:
            context['show_attach'] = False
        context['volume'] = volume
        if self.request.is_ajax():
            context['hide'] = True
        return context

    def get(self, request, *args, **kwargs):
        # Table action handling
        handled = self.construct_tables()
        if handled:
            return handled
        return self.render_to_response(self.get_context_data(**kwargs))

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.get(request, *args, **kwargs)
