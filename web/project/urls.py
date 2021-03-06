from django.conf.urls import patterns, include, url
from django.core.urlresolvers import reverse_lazy
from django.views.generic import RedirectView

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'aacalc.views.home', name='home'),
    # url(r'^aacalc/', include('aacalc.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
    url(r'^$', 'aacalc.views.home.home', name='home'),
    url(r'^about$', 'aacalc.views.about.about', name='about'),
    url(r'^privacy_policy$', 'aacalc.views.privacy_policy.privacy_policy', name='privacy_policy'),
    #url(r'^scenarios/edit$', 'aacalc.views.scenario_edit.scenario_edit', {'mode': 'edit'}, name='scenario_edit'),
    #url(r'^scenarios/results$', 'aacalc.views.scenario_run.scenario_run', name='scenario_run'),
    #url(r'^calculators/opal/aa$', 'aacalc.views.scenario_edit.scenario_edit', {'mode': 'aa'}, name='start_opal_aa'),
    #url(r'^calculators/opal/number$', 'aacalc.views.scenario_edit.scenario_edit', {'mode': 'number'}, name='start_opal_number'),
    url(r'^calculators/aa$', 'aacalc.views.alloc.alloc', {'mode': 'aa'}, name='start_aa'),
    url(r'^calculators/number$', 'aacalc.views.alloc.alloc', {'mode': 'number'}, name='start_number'),
    url(r'^calculators/retire$', 'aacalc.views.alloc.alloc', {'mode': 'retire'}, name='start_retire'),
    url(r'^calculators/le$', 'aacalc.views.le.le', name='start_le'),
    url(r'^calculators/spia$', 'aacalc.views.spia.spia', name='start_spia'),
    url(r'^docs/?$', RedirectView.as_view(url=reverse_lazy('aacalc.views.about.about'), permanent=False)),
    url(r'^docs/(.*)$', 'aacalc.views.docs.docs', name='docs'),
    url(r'^file/(.*)$', 'aacalc.views.file.file', name='file'),
    #url(r'^sample$', 'aacalc.views.sample.sample', name='sample'),
    url(r'^healthcheck$', 'aacalc.views.healthcheck.healthcheck'),
)
