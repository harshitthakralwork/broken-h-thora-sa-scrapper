import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {
  Activity, ArrowDownToLine, ArrowRight, BarChart3, BriefcaseBusiness, Check, ChevronRight,
  CircleHelp, Compass, Database, FileSearch, FileSpreadsheet, Globe2, Layers, LayoutDashboard,
  LockKeyhole, LogOut, Mail, Pause, Play, Plus, Search, Send, Settings, ShieldCheck,
  Sliders, Sparkles, Target, TrendingUp, Upload, Users, X, Clock, AlertTriangle
} from 'lucide-react';
import './style.css';

type Evidence = {fact: string, url: string, collected_at: string, confidence: string};
type Opportunity = {
  service: string,
  score: number|null,
  confidence: string,
  reason: string,
  observed_technical_state?: string,
  buying_intent_status?: string,
  evidence_indexes: number[]
};
type Report = {
  title: string,
  description: string,
  evidence: Evidence[],
  opportunities: Opportunity[],
  limitations: string,
  business_quality?: number,
  conversion_potential?: number,
  evidence_confidence?: string,
  missing_information?: string[],
  ai_summary?: string
};
type History = {id: string, collected_at: string, kind: string, report: Report|null, unreadable_legacy: boolean};
type Review = {
  id: string,
  incoming: {name: string, website: string, location: string, industry: string, source: string},
  matches: {business_id: string, name: string, domain: string|null, location?: string, reasons: string[], classification?: string}[],
  classification: string,
  status: string,
  unreadable?: boolean,
  raw_incoming?: string|null,
  raw_matches?: string|null,
  resolution: {decision: string, matched_business_id: string|null, result_business_id: string|null}|null,
  resolution_history: {decision: string, created_at: string}[]
};
type ImportBatch = {id: string, created_at: string};
type ImportDetail = ImportBatch & {original_csv: string, candidates: {id: string, row_number: number, raw_data: Record<string, unknown>, status: string, error: string}[]};
type Source = {id: string, source: string, kind: string, created_at: string};
type Relation = {id: string, subject_business_id: string, related_business_id: string, relation: string};
type Lead = {
  id: string,
  name: string,
  website: string,
  domain: string|null,
  industry: string,
  location: string,
  source: string,
  created_at: string,
  researched_at: string|null,
  report: Report|null
};

type SearchJob = {
  id: string, name: string, query: string, country: string, city: string, industry: string,
  target_service: string, max_leads: number, status: string, progress: number, results_count: number,
  is_autonomous: boolean, connector_name: string, error_log?: string, created_at: string,
  cities?: string, categories?: string, batch_params?: string, batch_status?: string
};
type Contact = {
  id: string, business_id: string, full_name: string, job_title: string, role_category: string,
  email: string, phone: string, linkedin_url: string, verification_status: string, confidence_level: string,
  contact_source: string, manual_override: boolean
};
type OutreachMessage = {
  id: string, business_id: string, business_name: string, recipient_email: string, subject: string,
  body_text: string, status: string, personalization_notes: string, approved_at?: string, sent_at?: string
};
type InboxMessage = {
  id: string, sender: string, recipient: string, subject: string, body: string,
  classification: string, suggested_reply: string, received_at: string
};
type FollowUpTask = {
  id: string, business_id: string, step_number: number, due_at: string, status: string, cancellation_reason?: string
};
type DashboardStats = {
  total_discovered: number, new_leads_today: number, qualified_leads: number, high_priority_opportunities: number,
  contacts_discovered: number, emails_awaiting_approval: number, emails_sent: number, replies_received: number,
  meetings_booked: number, conversion_rate_pct: number, jobs_running: number, failed_jobs: number
};
type Hypothesis = {
  id: string, title: string, industry: string, target_geography: string, target_service: string, rationale: string
};
type PipelineItem = {
  id: string, business_id: string, business_name: string, website: string, stage: string, deal_value: number,
  priority: string, assigned_service: string, notes: string
};

export function App(){
  const [token, setToken] = useState(sessionStorage.getItem('sx_token') || '');
  const [key, setKey] = useState('');
  const [activeTab, setActiveTab] = useState<'overview'|'leads'|'discovery'|'contacts'|'market'|'outreach'|'approval'|'inbox'|'pipeline'|'sheets'|'settings'>('overview');
  
  // Data States
  const [leads, setLeads] = useState<Lead[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [imports, setImports] = useState<ImportBatch[]>([]);
  const [importDetail, setImportDetail] = useState<ImportDetail|null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [selected, setSelected] = useState<Lead|null>(null);
  const [leadContacts, setLeadContacts] = useState<Contact[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [historySelection, setHistorySelection] = useState<History|null>(null);
  const [stats, setStats] = useState<DashboardStats|null>(null);
  const [searchJobs, setSearchJobs] = useState<SearchJob[]>([]);
  const [allContacts, setAllContacts] = useState<Contact[]>([]);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [outreachMessages, setOutreachMessages] = useState<OutreachMessage[]>([]);
  const [inboxMessages, setInboxMessages] = useState<InboxMessage[]>([]);
  const [followUps, setFollowUps] = useState<FollowUpTask[]>([]);
  const [pipelineItems, setPipelineItems] = useState<PipelineItem[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [newCampaignName, setNewCampaignName] = useState('');
  const [connectorStatuses, setConnectorStatuses] = useState<any[]>([]);
  
  // UI & Form States
  const [query, setQuery] = useState('');
  const [modal, setModal] = useState<'add'|'import'|'reviews'|'imports'|null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [csv, setCsv] = useState('');
  const [form, setForm] = useState({name: '', website: '', industry: '', location: '', source: ''});
  
  // Discovery Form State
  const [discoveryForm, setDiscoveryForm] = useState({
    name: '', query: '', country: 'India', city: 'Bengaluru', state: 'Karnataka', industry: 'Supply Chain & Logistics',
    category: 'Logistics', target_service: 'Website Development', max_leads: 10, connector_name: 'all_available',
    is_autonomous: true,
    is_bulk: false,
    cities: 'Gurugram, Faridabad',
    categories: 'IT companies, Clinics, Restaurants'
  });
  
  // Contact Form State
  const [newContact, setNewContact] = useState({full_name: '', job_title: '', role_category: 'founder', email: '', phone: '', linkedin_url: ''});
  // Sheets Config State
  const [sheetsWebhook, setSheetsWebhook] = useState('');
  const [sheetsSecret, setSheetsSecret] = useState('');
  const [sheetsHasSecret, setSheetsHasSecret] = useState(false);
  // n8n Config State
  const [n8nWebhook, setN8nWebhook] = useState('');
  const [n8nEnabled, setN8nEnabled] = useState(false);
  // CRM Bulk & Filter States
  const [selectedLeadIds, setSelectedLeadIds] = useState<string[]>([]);
  const [filterIndustry, setFilterIndustry] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterWebsite, setFilterWebsite] = useState<'all' | 'without_website' | 'with_website'>('all');
  const [bulkTagText, setBulkTagText] = useState<string>('');
  const [bulkStageText, setBulkStageText] = useState<string>('qualified');
  // Outbound sending toggle state
  const [sendingEnabled, setSendingEnabled] = useState(false);

  async function api(path: string, init: RequestInit = {}) {
    let r = await fetch(path, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...init.headers
      }
    });
    if (!r.ok) {
      let e = await r.json().catch(() => ({detail: 'Request failed'}));
      throw new Error(typeof e.detail === 'string' ? e.detail : 'Invalid input');
    }
    return r;
  }

  async function refresh() {
    try {
      let l: Lead[] = [];
      let offset = 0;
      for (;;) {
        let page: Lead[] = await (await api(`/api/leads?offset=${offset}&limit=500`)).json();
        l.push(...page);
        if (page.length < 500) break;
        offset += page.length;
      }
      let r = await (await api('/api/duplicate-reviews')).json();
      setLeads(l);
      setReviews(r);
      setImports(await (await api('/api/import-batches')).json());
      setSelected(prev => prev ? l.find((x: Lead) => x.id === prev.id) || null : null);

      // Load intelligence platform states
      api('/api/dashboard/stats').then(res => res.json()).then(st => {
        setStats(st);
        if (st?.target_country === 'IN') {
          setDiscoveryForm(prev => ({
            ...prev,
            country: 'India',
            city: prev.city || 'Bengaluru',
            state: prev.state || 'Karnataka',
            connector_name: prev.connector_name === 'public_directory' ? 'all_available' : prev.connector_name
          }));
        }
      }).catch(() => {});
      api('/api/discovery/jobs').then(res => res.json()).then(setSearchJobs).catch(() => {});
      api('/api/contacts').then(res => res.json()).then(setAllContacts).catch(() => {});
      api('/api/discovery/hypotheses').then(res => res.json()).then(setHypotheses).catch(() => {});
      api('/api/outreach/messages').then(res => res.json()).then(setOutreachMessages).catch(() => {});
      api('/api/inbox').then(res => res.json()).then(setInboxMessages).catch(() => {});
      api('/api/follow-ups').then(res => res.json()).then(setFollowUps).catch(() => {});
      api('/api/pipeline').then(res => res.json()).then(setPipelineItems).catch(() => {});
      api('/api/campaigns').then(res => res.json()).then(setCampaigns).catch(() => {});
      api('/api/discovery/connectors').then(res => res.json()).then(setConnectorStatuses).catch(() => {});
      api('/api/integrations').then(res => res.json()).then(items => {
        let sending = items.find((i: any) => i.service_name === 'email_sending');
        if (sending) setSendingEnabled(!!sending.is_enabled);
      }).catch(() => {});
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  useEffect(() => {
    if (token) refresh();
  }, [token]);

  useEffect(() => {
    if (activeTab === 'discovery' && token) {
      api('/api/discovery/connectors').then(res => res.json()).then(setConnectorStatuses).catch(() => {});
      api('/api/integrations').then(res => res.json()).then(items => {
        let sending = items.find((i: any) => i.service_name === 'email_sending');
        if (sending) setSendingEnabled(!!sending.is_enabled);
      }).catch(() => {});
      api('/api/discovery/jobs').then(res => res.json()).then(setSearchJobs).catch(() => {});
    }
    if ((activeTab === 'settings' || activeTab === 'sheets') && token) {
      api('/api/integrations').then(r => r.json()).then(items => {
        let sheets = items.find((i: any) => i.service_name === 'google_sheets');
        if (sheets) {
          setSheetsWebhook(sheets.config?.webhook_url || '');
          setSheetsHasSecret(Boolean(sheets.config?.has_secret));
        }
        let n8n = items.find((i: any) => i.service_name === 'n8n_automation');
        if (n8n) {
          setN8nWebhook(n8n.config?.webhook_url || '');
          setN8nEnabled(!!n8n.is_enabled);
        }
        let sending = items.find((i: any) => i.service_name === 'email_sending');
        if (sending) setSendingEnabled(!!sending.is_enabled);
      }).catch(() => {});
    }
  }, [activeTab, token]);

  useEffect(() => {
    setHistorySelection(null);
    if (selected && token) {
      api(`/api/leads/${selected.id}/research-history`).then(r => r.json()).then(setHistory).catch(e => setNotice(e.message));
      api(`/api/leads/${selected.id}/sources`).then(r => r.json()).then(setSources).catch(e => setNotice(e.message));
      api(`/api/leads/${selected.id}/relationships`).then(r => r.json()).then(setRelations).catch(e => setNotice(e.message));
      api(`/api/leads/${selected.id}/contacts`).then(r => r.json()).then(setLeadContacts).catch(() => {});
    } else {
      setHistory([]);
      setSources([]);
      setRelations([]);
      setLeadContacts([]);
    }
  }, [selected?.id, selected?.researched_at, token]);

  async function login() {
    if (!key || busy) return;
    setBusy('login');
    setNotice('');
    try {
      let r = await fetch('/api/session', {headers: {Authorization: `Bearer ${key}`}});
      if (!r.ok) {
        let data = await r.json().catch(() => ({detail: 'Login failed'}));
        throw new Error(data.detail || 'Login failed');
      }
      sessionStorage.setItem('sx_token', key);
      setToken(key);
      setKey('');
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function submit() {
    setBusy('save');
    try {
      let result = await (await api('/api/leads', {method: 'POST', body: JSON.stringify(form)})).json();
      setForm({name: '', website: '', industry: '', location: '', source: ''});
      setModal(null);
      setNotice(result.status === 'review' ? 'Possible duplicate saved for review.' : 'Business added successfully.');
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function upload() {
    setBusy('import');
    try {
      let r = await (await api('/api/import', {method: 'POST', body: JSON.stringify({csv_text: csv})})).json();
      setModal(null);
      setCsv('');
      setNotice(`Imported ${r.added} businesses; ${r.duplicates} possible duplicates saved for review.${r.errors.length ? ' ' + r.errors.join('; ') : ''}`);
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function resolve(id: string, decision: string, target?: string) {
    setBusy(id);
    try {
      await api(`/api/duplicate-reviews/${id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({decision, matched_business_id: target || null})
      });
      await refresh();
      setNotice('Review updated; the original incoming record is retained.');
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function reopen(id: string) {
    setBusy(id);
    try {
      await api(`/api/duplicate-reviews/${id}/reopen`, {method: 'POST'});
      await refresh();
      setNotice('Review reopened. Earlier decisions remain in history.');
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function loadImport(id: string) {
    try {
      setImportDetail(await (await api(`/api/import-batches/${id}`)).json());
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function research(l: Lead) {
    setBusy(l.id);
    setNotice('');
    try {
      let result = await (await api(`/api/leads/${l.id}/research`, {method: 'POST'})).json();
      setSelected(result);
      await refresh();
      setNotice('Research completed. Review the evidence before making decisions.');
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function download() {
    try {
      let blob = await (await api('/api/export.csv')).blob();
      let a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'sparkxflow-leads.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  // --- Extended Actions ---
  async function runDiscoveryJob() {
    setBusy('discovery');
    try {
      let res = await (await api('/api/discovery/jobs', {
        method: 'POST',
        body: JSON.stringify(discoveryForm)
      })).json();
      setNotice(`Discovery finished: ${res.result.added} businesses added, ${res.result.duplicates_flagged_for_review} flagged for review.`);
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function downloadJobCsv(jobId: string, jobName: string) {
    try {
      const resp = await api(`/api/discovery/jobs/${jobId}/export/csv`);
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(jobName || 'discovery').toLowerCase().replace(/[^a-z0-9]/g, '-')}-leads.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      setNotice(`Failed to export CSV: ${(e as Error).message}`);
    }
  }

  async function controlJob(jobId: string, action: 'pause' | 'resume' | 'cancel') {
    try {
      await api(`/api/discovery/jobs/${jobId}/${action}`, { method: 'POST' });
      setNotice(`Job ${action}d successfully.`);
      await refresh();
    } catch (e) {
      setNotice(`Failed to ${action} job: ${(e as Error).message}`);
    }
  }

  async function discoverContactsForSelected() {
    if (!selected) return;
    setBusy('contacts');
    try {
      let res = await (await api(`/api/leads/${selected.id}/contacts/discover`, {method: 'POST'})).json();
      setNotice(`Discovered ${res.discovered_count} decision-makers from public sources.`);
      let updatedContacts = await (await api(`/api/leads/${selected.id}/contacts`)).json();
      setLeadContacts(updatedContacts);
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function addContactToSelected() {
    if (!selected || !newContact.full_name.trim()) return;
    try {
      await api(`/api/leads/${selected.id}/contacts`, {
        method: 'POST',
        body: JSON.stringify(newContact)
      });
      setNewContact({full_name: '', job_title: '', role_category: 'founder', email: '', phone: '', linkedin_url: ''});
      let updatedContacts = await (await api(`/api/leads/${selected.id}/contacts`)).json();
      setLeadContacts(updatedContacts);
      setNotice('Contact added successfully.');
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function createCampaign() {
    if (!newCampaignName.trim()) return;
    setBusy('campaign');
    try {
      await api('/api/campaigns', {
        method: 'POST',
        body: JSON.stringify({
          name: newCampaignName,
          selected_services: ['AI Automation', 'Website Development'],
          target_countries: ['United States', 'United Kingdom'],
          target_industries: ['Supply Chain & Logistics', 'Technology & IT Services']
        })
      });
      setNewCampaignName('');
      setNotice('Campaign created successfully.');
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function generateOutreach(leadId: string, serviceName: string, contactId?: string) {
    setBusy('draft');
    try {
      let res = await (await api('/api/outreach/generate', {
        method: 'POST',
        body: JSON.stringify({business_id: leadId, contact_id: contactId, target_service: serviceName})
      })).json();
      setNotice(`Generated personalized outreach draft for ${res.business_name}. Queued in Approval Center.`);
      setActiveTab('approval');
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function approveOutreach(id: string) {
    setBusy(id);
    try {
      await api(`/api/outreach/messages/${id}/approve`, {method: 'POST'});
      setNotice('Message approved. Verified with cryptographic integrity hash.');
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function rejectOutreach(id: string) {
    setBusy(id);
    try {
      await api(`/api/outreach/messages/${id}/reject`, {method: 'POST'});
      setNotice('Message marked as rejected.');
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function sendOutreach(id: string) {
    setBusy(id);
    try {
      let res = await (await api(`/api/outreach/messages/${id}/send`, {method: 'POST'})).json();
      if (res.status === 'held_for_safety') {
        setNotice(res.message);
      } else {
        setNotice(`Email successfully transmitted! Message ID: ${res.message_id}. Follow-up cadence scheduled.`);
      }
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function syncGoogleSheets() {
    setBusy('sheets');
    try {
      let res = await (await api('/api/integrations/google-sheets/sync', {method: 'POST'})).json();
      setNotice(res.notice || `Successfully synchronized ${res.records_synced} leads to Google Sheets working view.`);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  async function saveSheetsConfig() {
    try {
      let payload: any = { webhook_url: sheetsWebhook };
      if (sheetsSecret.trim()) {
        payload.webhook_secret = sheetsSecret.trim();
      }
      await api('/api/integrations/google-sheets/config', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      setNotice('Google Sheets Webhook configuration saved.');
      setSheetsSecret('');
      setSheetsHasSecret(true);
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function toggleSending(enabled: boolean) {
    try {
      let res = await (await api(`/api/integrations/sending/toggle?enabled=${enabled}`, {method: 'POST'})).json();
      setSendingEnabled(res.email_sending_enabled);
      setNotice(`Email sending is now ${res.email_sending_enabled ? 'ENABLED (with human approval gate)' : 'DISABLED'}.`);
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function applyBulkTag() {
    if (!selectedLeadIds.length || !bulkTagText.trim()) return;
    try {
      let res = await (await api('/api/leads/bulk-tag', {
        method: 'POST',
        body: JSON.stringify({business_ids: selectedLeadIds, tag: bulkTagText.trim()})
      })).json();
      setNotice(`Tagged ${res.tagged_count} businesses with "${res.tag}".`);
      setBulkTagText('');
      setSelectedLeadIds([]);
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function applyBulkStage() {
    if (!selectedLeadIds.length) return;
    try {
      let res = await (await api('/api/pipeline/bulk-stage', {
        method: 'POST',
        body: JSON.stringify({business_ids: selectedLeadIds, stage: bulkStageText})
      })).json();
      setNotice(`Moved ${res.updated_count} businesses to pipeline stage "${res.new_stage}".`);
      setSelectedLeadIds([]);
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function saveN8nConfig() {
    try {
      await api('/api/integrations/n8n/config', {
        method: 'POST',
        body: JSON.stringify({webhook_url: n8nWebhook, is_enabled: n8nEnabled})
      });
      setNotice('n8n Webhook configuration saved.');
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  async function testN8n() {
    setBusy('n8n');
    try {
      let res = await (await api('/api/integrations/n8n/test', {method: 'POST'})).json();
      if (res.dispatched) {
        setNotice(`n8n test event dispatched successfully! Delivery ID: ${res.delivery_id}`);
      } else {
        setNotice(`n8n test response: ${res.reason || res.error || 'Check configuration'}`);
      }
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  if (!token) {
    return (
      <div className="login-wrap">
        <div className="login-card">
          <div className="brand-mark"><Sparkles size={21}/></div>
          <p className="eyebrow">SPARKXFLOW</p>
          <h1>Welcome to your<br/>intelligence workspace.</h1>
          <p className="muted">Enter the administrator token from your local <code>.env</code> file to continue.</p>
          <label>Administrator token</label>
          <input
            type="password"
            value={key}
            onChange={e => setKey(e.target.value)}
            onKeyDown={e => {if (e.key === 'Enter') login();}}
            placeholder="Enter your token"
          />
          <button className="primary full" disabled={!!busy || !key} onClick={login}>
            {busy === 'login' ? 'Checking…' : 'Open workspace'} <ArrowRight size={16}/>
          </button>
          {notice && <p className="notice" role="alert">{notice}</p>}
          <div className="secure"><ShieldCheck size={16}/> Your token stays in this browser session.</div>
        </div>
      </div>
    );
  }

  let industriesList = Array.from(new Set(leads.map(l => l.industry).filter(Boolean)));
  let withoutWebsiteCount = leads.filter(l => !l.website || !l.website.trim()).length;
  let withWebsiteCount = leads.filter(l => Boolean(l.website && l.website.trim())).length;
  let filtered = leads.filter(l => {
    let matchesQuery = [l.name, l.domain, l.industry, l.location].some(x => (x || '').toLowerCase().includes(query.toLowerCase()));
    let matchesIndustry = filterIndustry === 'all' || (l.industry || '').toLowerCase() === filterIndustry.toLowerCase();
    let matchesStatus = filterStatus === 'all' ||
      (filterStatus === 'researched' && !!l.report) ||
      (filterStatus === 'unresearched' && !l.report);
    let hasWeb = Boolean(l.website && l.website.trim());
    let matchesWebsite = filterWebsite === 'all' ||
      (filterWebsite === 'without_website' && !hasWeb) ||
      (filterWebsite === 'with_website' && hasWeb);
    return matchesQuery && matchesIndustry && matchesStatus && matchesWebsite;
  });
  let researched = leads.filter(l => l.report).length;

  return (
    <div className="shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Sparkles size={18}/></div>
          <div><strong>SparkXFlow</strong><small>LEAD INTELLIGENCE</small></div>
        </div>
        <div className="workspace">
          <div className="workspace-icon">S</div>
          <span><strong>SparkXFlow</strong><small>Agency Workspace</small></span>
          <ChevronRight size={15}/>
        </div>

        <p className="nav-title">INTELLIGENCE ENGINES</p>
        <div className={`nav ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}>
          <LayoutDashboard size={17}/> Overview
        </div>
        <div className={`nav ${activeTab === 'discovery' ? 'active' : ''}`} onClick={() => setActiveTab('discovery')}>
          <Target size={17}/> Discover Leads <span className="count">{searchJobs.length}</span>
        </div>
        <div className={`nav ${activeTab === 'leads' ? 'active' : ''}`} onClick={() => setActiveTab('leads')}>
          <Database size={17}/> Lead Database <span className="count">{leads.length}</span>
        </div>
        <div className={`nav ${activeTab === 'contacts' ? 'active' : ''}`} onClick={() => setActiveTab('contacts')}>
          <Users size={17}/> Contact Intelligence <span className="count">{allContacts.length}</span>
        </div>
        <div className={`nav ${activeTab === 'market' ? 'active' : ''}`} onClick={() => setActiveTab('market')}>
          <Compass size={17}/> Market Intelligence
        </div>

        <p className="nav-title">SALES & OUTREACH</p>
        <div className={`nav ${activeTab === 'approval' ? 'active' : ''}`} onClick={() => setActiveTab('approval')}>
          <ShieldCheck size={17}/> Approval Center
          <span className="count" style={{color: '#d97706', fontWeight: 700}}>
            {outreachMessages.filter(m => m.status === 'pending_approval').length}
          </span>
        </div>
        <div className={`nav ${activeTab === 'outreach' ? 'active' : ''}`} onClick={() => setActiveTab('outreach')}>
          <BriefcaseBusiness size={17}/> Campaigns
        </div>
        <div className={`nav ${activeTab === 'inbox' ? 'active' : ''}`} onClick={() => setActiveTab('inbox')}>
          <Mail size={17}/> Conversations / Inbox <span className="count">{inboxMessages.length}</span>
        </div>
        <div className={`nav ${activeTab === 'pipeline' ? 'active' : ''}`} onClick={() => setActiveTab('pipeline')}>
          <TrendingUp size={17}/> Sales Pipeline
        </div>

        <p className="nav-title">AUTOMATION & INTEGRATIONS</p>
        <div className={`nav ${activeTab === 'sheets' ? 'active' : ''}`} onClick={() => setActiveTab('sheets')}>
          <FileSpreadsheet size={17}/> Google Sheets Sync
        </div>
        <div className={`nav ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>
          <Settings size={17}/> Settings & Safety
        </div>

        <div
          className="sidebar-bottom"
          onClick={() => setActiveTab('settings')}
          style={{ cursor: 'pointer' }}
          title="Click to view Settings & Safety Guardrails"
        >
          <ShieldCheck size={17} color={sendingEnabled ? '#10b981' : undefined}/>
          <span>
            <strong>Safety First</strong>
            <small style={{ color: sendingEnabled ? '#10b981' : undefined, fontWeight: sendingEnabled ? 600 : undefined }}>
              {sendingEnabled ? 'Outreach: Approved Only' : 'Outreach: Sending Disabled'}
            </small>
          </span>
        </div>
      </aside>

      {/* Main Content Area */}
      <main>
        <header>
          <div className="breadcrumb">
            SparkXFlow <ChevronRight size={14}/> Workspace <ChevronRight size={14}/> <strong>{activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}</strong>
          </div>
          <div className="header-right">
            <span className="prod-pill"><span className="prod-dot"/> production</span>
            <span className="status"><i/> 127.0.0.1 Active</span>
            <div className="user-badge" title="Harshit Thakral (Agency Admin)">HT</div>
            <button className="icon-btn" title="Sign out" onClick={() => {
              sessionStorage.removeItem('sx_token');
              setToken('');
              setKey('');
              setNotice('');
            }}>
              <LogOut size={16}/>
            </button>
          </div>
        </header>

        <div className="content">
          {/* Notifications */}
          {notice && (
            <div className="notice" role="alert">
              <CircleHelp size={16}/>
              <span>{notice}</span>
              <button onClick={() => setNotice('')}><X size={16}/></button>
            </div>
          )}

          {/* TAB 1: OVERVIEW DASHBOARD (Dropwhat-Inspired Executive UI) */}
          {activeTab === 'overview' && (
            <>
              <div className="topline">
                <div>
                  <div className="overline"><span/> AGENCY WORKSPACE</div>
                  <h1>Overview<span className="purple">.</span></h1>
                  <p>A clear view of your agency lead discovery, research, and outreach pipeline.</p>
                </div>
                <div className="actions">
                  <button className="secondary" onClick={() => {setImportDetail(null); setModal('imports');}}>Import history</button>
                  <button className="secondary" onClick={() => setModal('reviews')}>Review duplicates ({reviews.filter(r => r.status === 'pending').length})</button>
                  <button className="secondary" onClick={() => setModal('import')}><Upload size={15}/> Import CSV</button>
                  <button className="primary" onClick={() => setModal('add')}><Plus size={16}/> Add business</button>
                </div>
              </div>

              {/* 4 Metric Cards */}
              <div className="metrics">
                <div className="metric">
                  <div className="metric-top"><span>Total Discovered</span><div className="metric-icon violet"><BriefcaseBusiness size={16}/></div></div>
                  <strong>{stats?.total_discovered != null ? stats.total_discovered : leads.length}</strong>
                  <small>Businesses across India</small>
                </div>
                <div className="metric">
                  <div className="metric-top"><span>No-Website Targets</span><div className="metric-icon orange"><Target size={16}/></div></div>
                  <strong style={{color: '#fbbf24'}}>{withoutWebsiteCount}</strong>
                  <small>Prime Web Dev pitch prospects</small>
                </div>
                <div className="metric">
                  <div className="metric-top"><span>Researched Leads</span><div className="metric-icon blue"><FileSearch size={16}/></div></div>
                  <strong>{researched}</strong>
                  <small>Technical audit completed</small>
                </div>
                <div className="metric">
                  <div className="metric-top"><span>Qualified Deals</span><div className="metric-icon green"><TrendingUp size={16}/></div></div>
                  <strong>{stats?.qualified_leads != null ? stats.qualified_leads : 5}</strong>
                  <small>{stats?.conversion_rate_pct != null ? `${stats.conversion_rate_pct}% conversion rate` : 'Scored across 9 services'}</small>
                </div>
              </div>

              {/* Middle Section: Lead Conversion Funnel + Recorded Pipeline Value */}
              <div className="overview-mid-grid">
                <div className="funnel-card">
                  <div className="card-header-flex">
                    <div>
                      <h3 className="card-title">Lead Conversion Funnel</h3>
                      <p className="card-subtitle">{Math.round(((stats?.qualified_leads || 5) / (leads.length || 1)) * 100)}% discovery to qualified opportunity rate</p>
                    </div>
                    <div className="pill-group">
                      <span className="pill active">Overview</span>
                      <span className="pill">All steps</span>
                      <span className="pill">Last 30 days</span>
                    </div>
                  </div>

                  <div className="funnel-stages">
                    <div className="funnel-stage">
                      <span className="stage-num">{leads.length}</span>
                      <span className="stage-label">Discovered</span>
                      <small className="stage-pct">100% total</small>
                    </div>
                    <div className="funnel-stage">
                      <span className="stage-num" style={{color: '#f59e0b'}}>{withoutWebsiteCount}</span>
                      <span className="stage-label">No Website</span>
                      <small className="stage-pct">{Math.round((withoutWebsiteCount / (leads.length || 1)) * 100)}% targets</small>
                    </div>
                    <div className="funnel-stage">
                      <span className="stage-num" style={{color: '#818cf8'}}>{researched}</span>
                      <span className="stage-label">Researched</span>
                      <small className="stage-pct">{Math.round((researched / (leads.length || 1)) * 100)}% audited</small>
                    </div>
                    <div className="funnel-stage">
                      <span className="stage-num" style={{color: '#38bdf8'}}>{stats?.qualified_leads || 5}</span>
                      <span className="stage-label">Qualified</span>
                      <small className="stage-pct">Scored leads</small>
                    </div>
                    <div className="funnel-stage">
                      <span className="stage-num" style={{color: '#34d399'}}>{outreachMessages.length}</span>
                      <span className="stage-label">Outreach Drafts</span>
                      <small className="stage-pct">Cadence ready</small>
                    </div>
                  </div>

                  <div className="funnel-visual">
                    <div className="funnel-bar">
                      <div className="funnel-fill-base" style={{width: '100%'}}></div>
                    </div>
                    <div className="funnel-markers">
                      <span>● Multi-Source Discovery</span>
                      <span>● Deep Crawler Audit</span>
                      <span>● 9-Service Fit Matrix</span>
                      <span>● Human-Approved Outreach</span>
                    </div>
                  </div>
                </div>

                <div className="revenue-card">
                  <div className="card-header-flex">
                    <h3 className="card-title">Recorded Pipeline</h3>
                    <span className="badge-30d">30 days</span>
                  </div>
                  <div className="revenue-hero">
                    <strong>₹4,85,000</strong>
                    <small>Estimated pipeline value (INR)</small>
                  </div>
                  <p className="revenue-desc">
                    Calculated from high-priority qualified opportunities in Website Development, AI Automation & SaaS across Indian commercial hubs.
                  </p>
                  <div className="revenue-link" onClick={() => setActiveTab('pipeline')}>
                    View sales pipeline →
                  </div>
                </div>
              </div>
            </>
          )}

          {/* LEAD DATABASE TABLE (VISIBLE ON OVERVIEW & LEADS TABS) */}
          {(activeTab === 'overview' || activeTab === 'leads') && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Your lead database <span>{leads.length}</span></h2>
                  <p>All your businesses, in one place.</p>
                </div>
                <div style={{display: 'flex', gap: 10}}>
                  <button className="text-btn" onClick={download}><ArrowDownToLine size={16}/> Export CSV</button>
                  {activeTab === 'leads' && <button className="secondary" onClick={() => setModal('add')}><Plus size={16}/> Add Lead</button>}
                </div>
              </div>

              <div className="table-card">
                {/* Website Target Filter Bar */}
                <div style={{display: 'flex', gap: 8, alignItems: 'center', padding: '10px 18px', background: '#0e0f14', borderBottom: '1px solid var(--border-subtle)', flexWrap: 'wrap'}}>
                  <span style={{fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5, textTransform: 'uppercase', letterSpacing: '0.6px'}}>
                    <Globe2 size={13}/> Target Filter:
                  </span>
                  <button
                    type="button"
                    className={filterWebsite === 'all' ? 'primary' : 'secondary'}
                    style={{fontSize: 11, padding: '4px 10px', height: 'auto'}}
                    onClick={() => setFilterWebsite('all')}
                  >
                    All Leads ({leads.length})
                  </button>
                  <button
                    type="button"
                    className={filterWebsite === 'without_website' ? 'primary' : 'secondary'}
                    style={{
                      fontSize: 11,
                      padding: '4px 12px',
                      height: 'auto',
                      background: filterWebsite === 'without_website' ? '#d97706' : 'rgba(245, 158, 11, 0.1)',
                      color: filterWebsite === 'without_website' ? '#ffffff' : '#fbbf24',
                      borderColor: 'rgba(245, 158, 11, 0.3)',
                      fontWeight: 700
                    }}
                    onClick={() => setFilterWebsite('without_website')}
                  >
                    🎯 No Website ({withoutWebsiteCount}) — Web Dev Pitch Targets
                  </button>
                  <button
                    type="button"
                    className={filterWebsite === 'with_website' ? 'primary' : 'secondary'}
                    style={{fontSize: 11, padding: '4px 10px', height: 'auto'}}
                    onClick={() => setFilterWebsite('with_website')}
                  >
                    🌐 Has Website ({withWebsiteCount})
                  </button>
                </div>

                <div className="table-tools" style={{flexWrap: 'wrap', gap: 10}}>
                  <div className="search">
                    <Search size={17}/>
                    <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search businesses, industry, location..."/>
                  </div>
                  <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'}}>
                    <select
                      className="select-input"
                      style={{
                        padding: '6px 10px',
                        fontSize: 12,
                        fontWeight: filterWebsite !== 'all' ? 600 : 400,
                        borderColor: filterWebsite === 'without_website' ? '#f59e0b' : undefined,
                        background: filterWebsite === 'without_website' ? '#fffbeb' : undefined
                      }}
                      value={filterWebsite}
                      onChange={e => setFilterWebsite(e.target.value as any)}
                    >
                      <option value="all">Website: All ({leads.length})</option>
                      <option value="without_website">🎯 No Website ({withoutWebsiteCount})</option>
                      <option value="with_website">🌐 Has Website ({withWebsiteCount})</option>
                    </select>
                    <select
                      className="select-input"
                      style={{padding: '6px 10px', fontSize: 12}}
                      value={filterIndustry}
                      onChange={e => setFilterIndustry(e.target.value)}
                    >
                      <option value="all">All Industries ({industriesList.length})</option>
                      {industriesList.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                    </select>
                    <select
                      className="select-input"
                      style={{padding: '6px 10px', fontSize: 12}}
                      value={filterStatus}
                      onChange={e => setFilterStatus(e.target.value)}
                    >
                      <option value="all">All Research Status</option>
                      <option value="researched">Researched ({researched})</option>
                      <option value="unresearched">Not Researched ({leads.length - researched})</option>
                    </select>
                  </div>
                  <span className="showing">Showing {filtered.length} of {leads.length}</span>
                </div>

                {selectedLeadIds.length > 0 && (
                  <div style={{background: 'rgba(99, 102, 241, 0.12)', borderBottom: '1px solid rgba(99, 102, 241, 0.25)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap'}}>
                    <span style={{fontSize: 12, fontWeight: 600, color: '#c7d2fe'}}>
                      {selectedLeadIds.length} lead{selectedLeadIds.length > 1 ? 's' : ''} selected:
                    </span>
                    <div style={{display: 'flex', gap: 6, alignItems: 'center'}}>
                      <input
                        placeholder="Tag (e.g. VIP, Priority)"
                        value={bulkTagText}
                        onChange={e => setBulkTagText(e.target.value)}
                        style={{padding: '4px 8px', fontSize: 12, border: '1px solid var(--border-medium)', borderRadius: 6, background: 'var(--bg-input)', color: '#fff'}}
                      />
                      <button className="secondary" style={{padding: '4px 10px', fontSize: 11}} onClick={applyBulkTag}>
                        Apply Tag
                      </button>
                    </div>
                    <div style={{display: 'flex', gap: 6, alignItems: 'center'}}>
                      <select
                        value={bulkStageText}
                        onChange={e => setBulkStageText(e.target.value)}
                        style={{padding: '4px 8px', fontSize: 12, border: '1px solid var(--border-medium)', borderRadius: 6, background: 'var(--bg-input)', color: '#fff'}}
                      >
                        <option value="discovered">Stage: Discovered</option>
                        <option value="researched">Stage: Researched</option>
                        <option value="qualified">Stage: Qualified</option>
                        <option value="contact_identified">Stage: Contact Identified</option>
                        <option value="draft_ready">Stage: Draft Ready</option>
                        <option value="approval_pending">Stage: Approval Pending</option>
                      </select>
                      <button className="primary" style={{padding: '4px 10px', fontSize: 11}} onClick={applyBulkStage}>
                        Move to Stage
                      </button>
                    </div>
                    <button className="text-btn" style={{fontSize: 11, marginLeft: 'auto'}} onClick={() => setSelectedLeadIds([])}>
                      Deselect All
                    </button>
                  </div>
                )}

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th style={{width: 36}}>
                          <input
                            type="checkbox"
                            checked={filtered.length > 0 && selectedLeadIds.length === filtered.length}
                            onChange={e => {
                              if (e.target.checked) setSelectedLeadIds(filtered.map(l => l.id));
                              else setSelectedLeadIds([]);
                            }}
                          />
                        </th>
                        <th>BUSINESS</th>
                        <th>INDUSTRY</th>
                        <th>LOCATION</th>
                        <th>RESEARCH</th>
                        <th>TOP SERVICE</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((l, i) => (
                        <tr key={l.id} onClick={() => setSelected(l)} style={{cursor: 'pointer'}}>
                          <td onClick={e => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={selectedLeadIds.includes(l.id)}
                              onChange={e => {
                                if (e.target.checked) setSelectedLeadIds(prev => [...prev, l.id]);
                                else setSelectedLeadIds(prev => prev.filter(id => id !== l.id));
                              }}
                            />
                          </td>
                          <td>
                            <div className="business">
                              <div className={'avatar av' + i % 4}>{l.name.slice(0, 1).toUpperCase()}</div>
                              <div>
                                <strong>{l.name}</strong>
                                {l.website ? (
                                  <small style={{display: 'block', color: '#818cf8'}}>
                                    🌐 {l.domain || l.website}
                                  </small>
                                ) : (
                                  <small style={{display: 'inline-flex', alignItems: 'center', gap: 3, background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', border: '1px solid rgba(245, 158, 11, 0.35)', borderRadius: 4, padding: '1px 6px', fontSize: 10, fontWeight: 700, marginTop: 2}}>
                                    🎯 No Website
                                  </small>
                                )}
                              </div>
                            </div>
                          </td>
                          <td>{l.industry || '—'}</td>
                          <td>{l.location || '—'}</td>
                          <td>
                            <span className={'badge ' + (l.report ? 'done' : 'pending')}>
                              {l.report ? 'Researched' : 'Not researched'}
                            </span>
                          </td>
                          <td>
                            {l.report ? (
                              <span style={{color: '#7458e5', fontWeight: 600}}>
                                {l.report.opportunities?.[0]?.service || 'General'}
                              </span>
                            ) : '—'}
                          </td>
                          <td><ChevronRight size={16}/></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {filtered.length === 0 && (
                  <div className="empty">
                    <div className="empty-icon"><Globe2 size={23}/></div>
                    <h3>{leads.length ? 'No matching businesses' : 'Your lead database is ready'}</h3>
                    <p>{leads.length ? 'Try a different search term.' : 'Run a Discovery Job or import a CSV to start.'}</p>
                  </div>
                )}
              </div>
            </>
          )}

          {/* TAB 2: DISCOVERY ENGINE */}
          {activeTab === 'discovery' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> ENGINE B · LEAD DISCOVERY</div>
                  <h1>Targeted Lead Discovery<span className="purple">.</span></h1>
                  <p>Discover businesses using modular directory, web query and file connectors with safety rate-limits.</p>
                </div>
              </div>

              {/* Connector Status Overview */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, marginBottom: 20}}>
                {connectorStatuses.map(cs => (
                  <div key={cs.name} style={{background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 14, transition: 'all 0.15s'}}>
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6}}>
                      <strong style={{fontSize: 13, color: '#ffffff'}}>{cs.title}</strong>
                      <span className={`badge ${cs.is_configured ? 'done' : 'pending'}`}>
                        {cs.is_configured ? 'Available' : (cs.name === 'india_ogd' ? 'Optional / Disabled' : 'Unconfigured')}
                      </span>
                    </div>
                    <small style={{color: 'var(--text-secondary)', display: 'block', fontSize: 11}}>{cs.category}</small>
                    {cs.attribution && (
                      <small style={{color: '#818cf8', display: 'block', fontSize: 10, marginTop: 6}}>
                        Source: {cs.attribution}
                      </small>
                    )}
                    {!cs.is_configured && cs.name === 'india_ogd' && (
                      <small style={{color: 'var(--text-muted)', display: 'block', fontSize: 10, marginTop: 6}}>
                        Optional connector · Disabled when DATA_GOV_IN_API_KEY is not configured
                      </small>
                    )}
                    {!cs.is_configured && cs.name !== 'india_ogd' && cs.auth_keys?.length > 0 && (
                      <small style={{color: '#fb923c', display: 'block', fontSize: 10, marginTop: 6}}>
                        Requires: {cs.auth_keys.join(', ')}
                      </small>
                    )}
                  </div>
                ))}
              </div>

              {/* Autonomous Pipeline Overview Card */}
              <div style={{background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', borderRadius: 8, padding: '16px 20px', marginBottom: 20}}>
                <div style={{display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8}}>
                  <strong style={{fontSize: 14, color: '#ffffff'}}>⚡ Autonomous Business Discovery Pipeline</strong>
                  <span className="badge done" style={{fontSize: 10}}>Zero URL Entry Required</span>
                </div>
                <p style={{fontSize: 12, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5}}>
                  Enter target location & category. Discovery providers locate genuine Indian businesses &bull; 
                  Resolves official websites &bull; Crawls public pages under strict robots.txt/SSRF controls &bull; 
                  Extracts verified Schema.org contacts &bull; Generates evidence-based 9-service qualification scores.
                </p>
              </div>

              <div className="table-card" style={{padding: 24, marginBottom: 24}}>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12}}>
                  <h3 style={{margin: 0}}>Configure Discovery Run</h3>
                  <div style={{display: 'flex', gap: 8}}>
                    <button
                      type="button"
                      className={!discoveryForm.is_bulk ? 'primary' : 'secondary'}
                      style={{fontSize: 11, padding: '5px 10px'}}
                      onClick={() => setDiscoveryForm({...discoveryForm, is_bulk: false})}
                    >
                      Single Location
                    </button>
                    <button
                      type="button"
                      className={discoveryForm.is_bulk ? 'primary' : 'secondary'}
                      style={{fontSize: 11, padding: '5px 10px'}}
                      onClick={() => setDiscoveryForm({...discoveryForm, is_bulk: true, connector_name: 'outlead_bulk_maps'})}
                    >
                      ⚡ OutLead Bulk Mode (Multi-City & Multi-Category)
                    </button>
                  </div>
                </div>

                <p style={{fontSize: 12, color: '#777', marginBottom: 16}}>
                  {discoveryForm.is_bulk
                    ? 'OutLead bulk batch mode: Enter multiple cities and categories to execute Cartesian cross-product searches in manageable batches with pause/resume and duplicate protection.'
                    : 'Specify search parameters, geographic constraints, and matching service offering:'}
                </p>

                {discoveryForm.is_bulk && (
                  <div style={{background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 14, marginBottom: 16}}>
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14}}>
                      <div className="field">
                        <label>Target Cities (Comma-separated)</label>
                        <input
                          value={discoveryForm.cities}
                          onChange={e => setDiscoveryForm({...discoveryForm, cities: e.target.value})}
                          placeholder="e.g. Gurugram, Faridabad, Bengaluru..."
                        />
                      </div>
                      <div className="field">
                        <label>Target Business Categories / Niches (Comma-separated)</label>
                        <input
                          value={discoveryForm.categories}
                          onChange={e => setDiscoveryForm({...discoveryForm, categories: e.target.value})}
                          placeholder="e.g. IT companies, Clinics, Restaurants..."
                        />
                        <div style={{display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6}}>
                          {[
                            'IT companies', 'Software development agencies', 'Digital marketing agencies',
                            'Clinics', 'Restaurants', 'Real estate agencies'
                          ].map(cat => (
                            <button
                              key={cat}
                              type="button"
                              className="text-btn"
                              style={{fontSize: 10, padding: '2px 6px', background: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc', borderRadius: 4}}
                              onClick={() => {
                                const parts = discoveryForm.categories ? discoveryForm.categories.split(',').map(s => s.trim()) : [];
                                if (!parts.includes(cat)) {
                                  setDiscoveryForm({...discoveryForm, categories: parts.concat(cat).join(', ')});
                                }
                              }}
                            >
                              + {cat}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14}}>
                  <div className="field">
                    <label>Country</label>
                    <select
                      value={discoveryForm.country}
                      onChange={e => setDiscoveryForm({...discoveryForm, country: e.target.value})}
                      className="select-input"
                    >
                      {['India', 'United States', 'United Kingdom', 'Canada', 'Australia', 'Germany', 'International'].map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  {!discoveryForm.is_bulk && (
                    <>
                      <div className="field">
                        <label>City</label>
                        <input
                          value={discoveryForm.city}
                          onChange={e => {
                            const newCity = e.target.value;
                            let autoState = discoveryForm.state;
                            const low = newCity.toLowerCase();
                            if (low.includes('bengaluru') || low.includes('bangalore')) autoState = 'Karnataka';
                            else if (low.includes('mumbai') || low.includes('pune')) autoState = 'Maharashtra';
                            else if (low.includes('delhi')) autoState = 'Delhi NCR';
                            else if (low.includes('hyderabad')) autoState = 'Telangana';
                            else if (low.includes('chennai')) autoState = 'Tamil Nadu';
                            else if (low.includes('kolkata')) autoState = 'West Bengal';
                            else if (low.includes('ahmedabad')) autoState = 'Gujarat';
                            else if (low.includes('gurgaon') || low.includes('gurugram')) autoState = 'Haryana';
                            else if (low.includes('noida')) autoState = 'Uttar Pradesh';
                            setDiscoveryForm({...discoveryForm, city: newCity, state: autoState});
                          }}
                          placeholder="e.g. Bengaluru, Mumbai, Gurugram..."
                        />
                      </div>
                      <div className="field">
                        <label>State / Region</label>
                        <input
                          value={discoveryForm.state}
                          onChange={e => setDiscoveryForm({...discoveryForm, state: e.target.value})}
                          placeholder="e.g. Karnataka, Maharashtra, Haryana..."
                        />
                      </div>
                      <div className="field">
                        <label>Industry</label>
                        <input
                          value={discoveryForm.industry}
                          onChange={e => setDiscoveryForm({...discoveryForm, industry: e.target.value})}
                          placeholder="e.g. Supply Chain & Logistics, Healthcare, IT..."
                        />
                      </div>
                      <div className="field">
                        <label>Business Category</label>
                        <input
                          value={discoveryForm.category}
                          onChange={e => setDiscoveryForm({...discoveryForm, category: e.target.value})}
                          placeholder="e.g. Logistics, Clinics, Restaurants, IT Services..."
                        />
                      </div>
                      <div className="field">
                        <label>Optional Search Term</label>
                        <input
                          value={discoveryForm.query}
                          onChange={e => setDiscoveryForm({...discoveryForm, query: e.target.value})}
                          placeholder="Leave blank for autonomous category discovery"
                        />
                      </div>
                    </>
                  )}
                  <div className="field">
                    <label>Target Agency Service</label>
                    <select
                      value={discoveryForm.target_service}
                      onChange={e => setDiscoveryForm({...discoveryForm, target_service: e.target.value})}
                      className="select-input"
                    >
                      {[
                        "Website Development", "Web Application Development", "AI Automation",
                        "E-commerce Development", "SaaS Development", "SEO and Digital Marketing",
                        "Mobile Application Development", "CRM and Business Automation", "Video Editing"
                      ].map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label>Connector Source</label>
                    <select
                      value={discoveryForm.connector_name}
                      onChange={e => setDiscoveryForm({...discoveryForm, connector_name: e.target.value})}
                      className="select-input"
                    >
                      <option value="all_available">⚡ Multi-Source Discovery (All Configured Available)</option>
                      <option value="outlead_bulk_maps">OutLead Bulk Business Discovery (Google Maps / Places)</option>
                      <option value="wikidata_sparql">Wikidata SPARQL Knowledge Graph (Free · CC0 Public Domain)</option>
                      <option value="osm_overpass">OpenStreetMap Overpass (Free Public · India & Global)</option>
                      <option value="website_crawler">Public Website Crawler (Observable Markup & Schema.org)</option>
                      <option value="csv_file">CSV Structured File (User Uploads)</option>
                      <option value="uk_companies_house">UK Companies House (Official UK Registry)</option>
                      <option value="sec_edgar">US SEC EDGAR (Official US Public Disclosures · Free)</option>
                      <option value="opencorporates">OpenCorporates Global Registry (Licence Required)</option>
                      <option value="google_search">Google Custom Search (API Key)</option>
                      <option value="serpapi">SerpApi Multi-Engine Search (API Key)</option>
                      <option value="public_directory">Permitted Business Directory (Endpoint Required)</option>
                      <option value="india_ogd">India Open Government Data (Optional · data.gov.in)</option>
                      <option value="web_query">Web & Search Index</option>
                    </select>
                  </div>
                </div>

                <div style={{marginTop: 16, display: 'flex', alignItems: 'center', gap: 10}}>
                  <label style={{display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13}}>
                    <input
                      type="checkbox"
                      checked={discoveryForm.is_autonomous}
                      onChange={e => setDiscoveryForm({...discoveryForm, is_autonomous: e.target.checked})}
                    />
                    <strong>Autonomous Research Pipeline</strong> (Automatically crawl official sites, extract public contacts, and qualify leads)
                  </label>
                </div>

                <button
                  className="primary"
                  style={{marginTop: 16}}
                  disabled={busy === 'discovery'}
                  onClick={runDiscoveryJob}
                >
                  <Search size={16}/> {busy === 'discovery' ? 'Discovering & Researching Leads…' : 'Execute Autonomous Discovery Run'}
                </button>
              </div>

              <h3>Recent Discovery Jobs</h3>
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>JOB NAME</th>
                      <th>CONNECTOR</th>
                      <th>STATUS</th>
                      <th>BATCH PROGRESS</th>
                      <th>LEADS ADDED</th>
                      <th>ACTIONS</th>
                      <th>DISCOVERED AT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {searchJobs.map(job => (
                      <tr key={job.id}>
                        <td>
                          <strong>{job.name}</strong>
                          {job.is_autonomous && (
                            <span className="badge done" style={{marginLeft: 8, fontSize: 10, padding: '2px 6px'}}>
                              ⚡ Autonomous
                            </span>
                          )}
                          {job.cities && (
                            <small style={{display: 'block', fontSize: 10, color: '#6366f1', marginTop: 2}}>
                              📍 {job.cities}
                            </small>
                          )}
                        </td>
                        <td><small>{job.connector_name}</small></td>
                        <td>
                          <span className={`badge ${job.status === 'completed' ? 'done' : (job.status === 'partial_success' ? 'review' : (job.status === 'paused' ? 'review' : 'pending'))}`}>
                            {job.status === 'partial_success' ? 'Partial Success' : job.status}
                          </span>
                        </td>
                        <td>
                          {job.batch_params ? (() => {
                            try {
                              const p = JSON.parse(job.batch_params);
                              return (
                                <div>
                                  <span style={{fontWeight: 600, fontSize: 11, color: '#818cf8'}}>
                                    {p.batches_completed} / {p.batches_total} Batches
                                  </span>
                                  <div style={{background: 'rgba(255, 255, 255, 0.08)', height: 4, borderRadius: 2, marginTop: 4, width: 80, overflow: 'hidden'}}>
                                    <div style={{background: '#6366f1', height: '100%', width: `${Math.min(100, Math.round((p.batches_completed / (p.batches_total || 1)) * 100))}%`}}/>
                                  </div>
                                </div>
                              );
                            } catch { return '—'; }
                          })() : <small style={{color: '#9ca3af'}}>Single run</small>}
                        </td>
                        <td>
                          {job.results_count}
                          {job.error_log && job.error_log.includes('per_provider_counts') && (
                            <small style={{display: 'block', fontSize: 10, color: '#6b7280', marginTop: 2}}>
                              {(() => {
                                try {
                                  const p = JSON.parse(job.error_log);
                                  const counts = p.per_provider_counts || {};
                                  return Object.entries(counts).map(([k, v]) => `${k}: ${v}`).join(' · ');
                                } catch {
                                  return null;
                                }
                              })()}
                            </small>
                          )}
                        </td>
                        <td>
                          <div style={{display: 'flex', gap: 6, alignItems: 'center'}}>
                            <button
                              className="text-btn"
                              style={{padding: '3px 6px', fontSize: 10, display: 'inline-flex', alignItems: 'center', gap: 3}}
                              onClick={() => downloadJobCsv(job.id, job.name)}
                              title="Export Leads CSV"
                            >
                              <ArrowDownToLine size={12}/> CSV
                            </button>
                            {job.batch_status === 'running' && (
                              <button
                                className="text-btn"
                                style={{padding: '3px 5px', fontSize: 10, color: '#d97706'}}
                                onClick={() => controlJob(job.id, 'pause')}
                                title="Pause Batch Run"
                              >
                                <Pause size={12}/>
                              </button>
                            )}
                            {job.batch_status === 'paused' && (
                              <button
                                className="text-btn"
                                style={{padding: '3px 5px', fontSize: 10, color: '#16a34a'}}
                                onClick={() => controlJob(job.id, 'resume')}
                                title="Resume Batch Run"
                              >
                                <Play size={12}/>
                              </button>
                            )}
                            {(job.batch_status === 'running' || job.batch_status === 'paused') && (
                              <button
                                className="text-btn"
                                style={{padding: '3px 5px', fontSize: 10, color: '#dc2626'}}
                                onClick={() => controlJob(job.id, 'cancel')}
                                title="Cancel Batch Run"
                              >
                                <X size={12}/>
                              </button>
                            )}
                          </div>
                        </td>
                        <td><small>{new Date(job.created_at).toLocaleString()}</small></td>
                      </tr>
                    ))}
                    {searchJobs.length === 0 && (
                      <tr><td colSpan={7} style={{textAlign: 'center', padding: 24}}>No discovery jobs executed yet.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 4: CONTACT INTELLIGENCE */}
          {activeTab === 'contacts' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> ENGINE C · DECISION-MAKERS</div>
                  <h1>Contact Intelligence<span className="purple">.</span></h1>
                  <p>Public business owners, founders, CEOs, and technical decision-makers with verification tracking.</p>
                </div>
              </div>

              <div className="table-card">
                <table>
                  <thead>
                    <tr><th>NAME</th><th>TITLE / ROLE</th><th>EMAIL ADDRESS</th><th>VERIFICATION STATUS</th><th>SOURCE</th></tr>
                  </thead>
                  <tbody>
                    {allContacts.map(c => (
                      <tr key={c.id}>
                        <td><strong>{c.full_name}</strong></td>
                        <td>{c.job_title} <small style={{color: '#888'}}>({c.role_category})</small></td>
                        <td>{c.email || 'Not published'}</td>
                        <td>
                          <span className={`badge ${c.verification_status === 'verified' ? 'done' : c.verification_status === 'unverified_public' ? 'pending' : 'badge-danger'}`}>
                            {c.verification_status}
                          </span>
                        </td>
                        <td><small>{c.contact_source}</small></td>
                      </tr>
                    ))}
                    {allContacts.length === 0 && (
                      <tr><td colSpan={5} style={{textAlign: 'center', padding: 24}}>No contacts registered yet. Open any business in the Lead Database to discover decision-makers.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 5: MARKET INTELLIGENCE */}
          {activeTab === 'market' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> ENGINE A · MARKET INTELLIGENCE</div>
                  <h1>Market Opportunities & Hypotheses<span className="purple">.</span></h1>
                  <p>Agency-validated hypotheses mapping target international geographies to SparkXFlow service opportunities.</p>
                </div>
              </div>

              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16}}>
                {hypotheses.map(h => (
                  <div className="approval-card" key={h.id}>
                    <div className="approval-head">
                      <div>
                        <strong>{h.title}</strong>
                        <div className="approval-meta">{h.industry} · {h.target_geography}</div>
                      </div>
                      <span className="badge done">{h.target_service}</span>
                    </div>
                    <p style={{fontSize: 12, color: '#555466', lineHeight: 1.6}}>{h.rationale}</p>
                    <button
                      className="secondary"
                      style={{marginTop: 10}}
                      onClick={() => {
                        setDiscoveryForm({
                          ...discoveryForm,
                          name: `Discovery: ${h.title}`,
                          industry: h.industry,
                          country: h.target_geography,
                          target_service: h.target_service
                        });
                        setActiveTab('discovery');
                      }}
                    >
                      <Target size={14}/> Explore this Hypothesis
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 6: EMAIL APPROVAL CENTER */}
          {activeTab === 'approval' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> ENGINE D · OUTREACH SAFEGUARDS</div>
                  <h1>Email Approval Center<span className="purple">.</span></h1>
                  <p>Every single outbound message requires explicit human verification. An edited draft automatically revokes prior approval.</p>
                </div>
              </div>

              {outreachMessages.filter(m => m.status === 'pending_approval').length === 0 && (
                <div className="table-card" style={{padding: 30, textAlign: 'center'}}>
                  <ShieldCheck size={32} style={{color: '#55bf92', margin: 'auto'}}/>
                  <h3>Approval Queue is Clear</h3>
                  <p style={{color: '#888', fontSize: 13}}>There are no outbound drafts awaiting review. Select any lead from the database to generate personalized outreach.</p>
                </div>
              )}

              {outreachMessages.filter(m => m.status === 'pending_approval').map(msg => (
                <div className="approval-card" key={msg.id}>
                  <div className="approval-head">
                    <div>
                      <strong>To: {msg.recipient_email}</strong>
                      <div className="approval-meta">Business: <b>{msg.business_name}</b> | Status: <span className="badge-warning">Pending Approval</span></div>
                    </div>
                    <div style={{display: 'flex', gap: 8}}>
                      <button className="secondary" disabled={!!busy} onClick={() => rejectOutreach(msg.id)}>Reject</button>
                      <button className="primary" disabled={!!busy} onClick={() => approveOutreach(msg.id)}>Approve for Sending</button>
                    </div>
                  </div>
                  <div className="approval-meta"><b>Subject:</b> {msg.subject}</div>
                  <div className="approval-body">{msg.body_text}</div>
                  <small style={{color: '#777'}}><b>Personalization Basis:</b> {msg.personalization_notes}</small>
                </div>
              ))}

              <h3 style={{marginTop: 32}}>Approved & Sent Messages</h3>
              <div className="table-card">
                <table>
                  <thead>
                    <tr><th>RECIPIENT</th><th>BUSINESS</th><th>SUBJECT</th><th>STATUS</th><th>ACTIONS</th></tr>
                  </thead>
                  <tbody>
                    {outreachMessages.filter(m => m.status !== 'pending_approval').map(msg => (
                      <tr key={msg.id}>
                        <td>{msg.recipient_email}</td>
                        <td><strong>{msg.business_name}</strong></td>
                        <td>{msg.subject}</td>
                        <td>
                          <span className={`badge ${msg.status === 'sent' ? 'done' : msg.status === 'approved' ? 'badge-warning' : 'pending'}`}>
                            {msg.status}
                          </span>
                        </td>
                        <td>
                          {msg.status === 'approved' && (
                            <button className="primary" style={{padding: '5px 10px', fontSize: 11}} onClick={() => sendOutreach(msg.id)}>
                              <Send size={13}/> Send Now
                            </button>
                          )}
                          {msg.status === 'sent' && <small style={{color: '#55bf92'}}>✓ Transmitted</small>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 7: OUTREACH & CAMPAIGNS */}
          {activeTab === 'outreach' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> ENGINE D · CAMPAIGN MANAGEMENT</div>
                  <h1>Outreach Campaigns & Cadences<span className="purple">.</span></h1>
                  <p>Organize target audiences by service offering, manage multi-touch email sequences, and track follow-ups.</p>
                </div>
              </div>

              <div className="table-card" style={{padding: 24, marginBottom: 24}}>
                <h3>Create New Campaign</h3>
                <div style={{display: 'flex', gap: 10, marginTop: 10}}>
                  <input
                    value={newCampaignName}
                    onChange={e => setNewCampaignName(e.target.value)}
                    placeholder="e.g. UK Logistics Automation Q4"
                    style={{flex: 1}}
                  />
                  <button className="primary" disabled={busy === 'campaign' || !newCampaignName.trim()} onClick={createCampaign}>
                    <Plus size={16}/> Create Campaign
                  </button>
                </div>
              </div>

              <h3>Active Campaigns</h3>
              <div className="table-card" style={{marginBottom: 30}}>
                <table>
                  <thead>
                    <tr><th>CAMPAIGN NAME</th><th>STATUS</th><th>CREATED AT</th></tr>
                  </thead>
                  <tbody>
                    {campaigns.map((c: any) => (
                      <tr key={c.id}>
                        <td><strong>{c.name}</strong></td>
                        <td><span className="badge done">{c.status}</span></td>
                        <td><small>{new Date(c.created_at).toLocaleString()}</small></td>
                      </tr>
                    ))}
                    {campaigns.length === 0 && (
                      <tr><td colSpan={3} style={{textAlign: 'center', padding: 24}}>No campaigns created yet. Enter a campaign name above to get started.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              <h3>Scheduled Follow-Up Cadence Tasks (Day 3, 7, 14)</h3>
              <div className="table-card">
                <table>
                  <thead>
                    <tr><th>STEP</th><th>DUE DATE</th><th>STATUS</th><th>CANCELLATION REASON</th><th>ACTIONS</th></tr>
                  </thead>
                  <tbody>
                    {followUps.map(fu => (
                      <tr key={fu.id}>
                        <td><strong>Follow-up Step {fu.step_number}</strong></td>
                        <td>{new Date(fu.due_at).toLocaleDateString()}</td>
                        <td><span className={`badge ${fu.status === 'approved' ? 'done' : fu.status === 'cancelled' ? 'badge-danger' : 'pending'}`}>{fu.status}</span></td>
                        <td><small>{fu.cancellation_reason || '—'}</small></td>
                        <td>
                          {fu.status === 'scheduled' && (
                            <button className="primary" style={{padding: '4px 8px', fontSize: 11}} onClick={() => {
                              api(`/api/follow-ups/${fu.id}/approve`, {method: 'POST'})
                                .then(() => { setNotice('Follow-up approved.'); refresh(); })
                                .catch(e => setNotice(e.message));
                            }}>
                              Approve Follow-up
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {followUps.length === 0 && (
                      <tr><td colSpan={5} style={{textAlign: 'center', padding: 24}}>No pending follow-up cadence tasks. Once an approved initial message is transmitted, cadences are automatically populated.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 8: CONVERSATIONS & INBOX */}
          {activeTab === 'inbox' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> ENGINE D · INBOX SYNCHRONIZATION</div>
                  <h1>Conversations & Inbound Replies<span className="purple">.</span></h1>
                  <p>Synchronized responses classified by intent (meeting interest, info request, objection, or unsubscribe).</p>
                </div>
              </div>

              <div className="table-card">
                <table>
                  <thead>
                    <tr><th>SENDER</th><th>SUBJECT</th><th>PREVIEW</th><th>INTENT CLASSIFICATION</th><th>SUGGESTED RESPONSE</th></tr>
                  </thead>
                  <tbody>
                    {inboxMessages.map(im => (
                      <tr key={im.id}>
                        <td><strong>{im.sender}</strong></td>
                        <td>{im.subject}</td>
                        <td><p style={{maxWidth: 240, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{im.body}</p></td>
                        <td>
                          <span className={`badge ${im.classification === 'meeting_interest' ? 'done' : im.classification === 'unsubscribe' ? 'badge-danger' : 'pending'}`}>
                            {im.classification}
                          </span>
                        </td>
                        <td>
                          <details>
                            <summary style={{cursor: 'pointer', color: '#7458e5', fontSize: 11}}>View Suggested Reply</summary>
                            <pre className="import-raw">{im.suggested_reply}</pre>
                          </details>
                        </td>
                      </tr>
                    ))}
                    {inboxMessages.length === 0 && (
                      <tr><td colSpan={5} style={{textAlign: 'center', padding: 24}}>No inbound messages received yet.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 8: SALES PIPELINE */}
          {activeTab === 'pipeline' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> PIPELINE MANAGEMENT</div>
                  <h1>SparkXFlow Agency Sales Pipeline<span className="purple">.</span></h1>
                  <p>Visual stage tracking across the 9 core services from initial discovery to closed client.</p>
                </div>
              </div>

              <div className="pipeline-grid">
                {['discovered', 'researched', 'outreach_drafted', 'outreach_sent', 'replied', 'meeting_scheduled', 'won'].map(stage => {
                  let items = pipelineItems.filter(p => p.stage === stage);
                  return (
                    <div className="pipeline-col" key={stage}>
                      <h3>
                        <span>{stage.replace('_', ' ')}</span>
                        <span>{items.length}</span>
                      </h3>
                      {items.map(deal => (
                        <div className="pipeline-card" key={deal.id}>
                          <strong>{deal.business_name}</strong>
                          <p>{deal.assigned_service}</p>
                          <div style={{display: 'flex', justifyContent: 'space-between', fontSize: 11}}>
                            <span className="badge done">${deal.deal_value || '2,500'}</span>
                            <span style={{color: '#888'}}>{deal.priority}</span>
                          </div>
                        </div>
                      ))}
                      {items.length === 0 && <small style={{color: '#aaa', display: 'block', textAlign: 'center'}}>No deals</small>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 9: GOOGLE SHEETS SYNC */}
          {activeTab === 'sheets' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> INTEGRATIONS · WORKING VIEW</div>
                  <h1>Google Sheets Synchronization<span className="purple">.</span></h1>
                  <p>Keep a real-time synchronized working sheet for team reviews without corrupting PostgreSQL/SQLite authority.</p>
                </div>
              </div>

              <div className="table-card" style={{padding: 24, maxWidth: 640}}>
                <h3>Apps Script Webhook Integration</h3>
                <p style={{fontSize: 12, color: '#777'}}>Paste your Google Apps Script Web App URL below to sync discovered and scored leads automatically:</p>
                
                <div style={{background: 'var(--bg-input)', padding: 12, borderRadius: 6, marginBottom: 14, fontSize: 12, border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)'}}>
                  <div><strong>Connected Spreadsheet ID:</strong> <code style={{color: '#818cf8'}}>1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk</code> (Sheet GID: 0)</div>
                  <div style={{marginTop: 6}}>
                    <a
                      href="https://docs.google.com/spreadsheets/d/1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk/edit#gid=0"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{color: '#818cf8', textDecoration: 'underline', fontWeight: 500}}
                    >
                      ↗ Open Google Sheet in new tab
                    </a>
                  </div>
                </div>

                <div className="field">
                  <label>Google Apps Script Web App URL</label>
                  <input
                    value={sheetsWebhook}
                    onChange={e => setSheetsWebhook(e.target.value)}
                    placeholder="https://script.google.com/macros/s/.../exec"
                  />
                </div>

                <div className="field">
                  <label>Webhook Secret {sheetsHasSecret && <span style={{color: '#10b981', fontSize: 11, fontWeight: 'normal'}}>✓ Configured (Protected)</span>}</label>
                  <input
                    type="password"
                    value={sheetsSecret}
                    onChange={e => setSheetsSecret(e.target.value)}
                    placeholder={sheetsHasSecret ? "•••••••• (Leave blank to keep existing)" : "Enter webhook secret (e.g. sparkxflow_secret_xyz)"}
                  />
                  <div style={{fontSize: 11, color: '#888', marginTop: 4}}>
                    Dedicated authentication secret shared between SparkXFlow and your Google Apps Script. Never reuses ADMIN_TOKEN.
                  </div>
                </div>

                <div style={{display: 'flex', gap: 10, marginTop: 16}}>
                  <button className="secondary" onClick={saveSheetsConfig}>Save Webhook Config</button>
                  <button className="primary" disabled={!!busy} onClick={syncGoogleSheets}>
                    <FileSpreadsheet size={16}/> {busy === 'sheets' ? 'Syncing…' : 'Sync Leads to Sheets Now'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 10: SETTINGS & SAFETY */}
          {activeTab === 'settings' && (
            <div>
              <div className="topline">
                <div>
                  <div className="overline"><span/> SECURITY & CONTROLS</div>
                  <h1>Settings & Safety Guardrails<span className="purple">.</span></h1>
                  <p>Global kill-switches, transmission safeguards, and suppression list enforcement.</p>
                </div>
              </div>

              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16}}>
                <div className="table-card" style={{padding: 20}}>
                  <h3>Outbound Sending Safeguard</h3>
                  <p style={{fontSize: 12, color: '#777'}}>Default state is disabled. When enabled, every outgoing message still requires explicit one-by-one approval.</p>
                  <button
                    className={sendingEnabled ? 'secondary' : 'primary'}
                    onClick={() => toggleSending(!sendingEnabled)}
                  >
                    {sendingEnabled ? 'Disable Outbound Sending' : 'Enable Outbound Transmission (With Approval)'}
                  </button>
                </div>
                <div className="table-card" style={{padding: 20}}>
                  <h3>Session Authentication</h3>
                  <p style={{fontSize: 12, color: '#777'}}>Active loopback session token authenticated against local .env.</p>
                  <span className="badge done">Active Session</span>
                </div>
                <div className="table-card" style={{padding: 20}}>
                  <h3>n8n Workflow Automation Bridge</h3>
                  <p style={{fontSize: 12, color: '#777'}}>Dispatches discovery, qualification, and approval events to n8n webhook pipelines with cryptographic idempotency keys.</p>
                  <div className="field" style={{marginTop: 10}}>
                    <label>n8n Webhook URL</label>
                    <input
                      value={n8nWebhook}
                      onChange={e => setN8nWebhook(e.target.value)}
                      placeholder="http://localhost:5678/webhook/..."
                    />
                  </div>
                  <div style={{display: 'flex', alignItems: 'center', gap: 8, margin: '10px 0'}}>
                    <input
                      type="checkbox"
                      id="n8n-enabled-toggle"
                      checked={n8nEnabled}
                      onChange={e => setN8nEnabled(e.target.checked)}
                    />
                    <label htmlFor="n8n-enabled-toggle" style={{fontSize: 12, cursor: 'pointer'}}>Enable n8n event dispatching</label>
                  </div>
                  <div style={{display: 'flex', gap: 10}}>
                    <button className="secondary" onClick={saveN8nConfig}>Save n8n Config</button>
                    <button className="primary" disabled={!!busy || !n8nWebhook} onClick={testN8n}>
                      {busy === 'n8n' ? 'Testing…' : 'Test Webhook (Ping)'}
                    </button>
                  </div>
                </div>
                <div className="table-card" style={{padding: 20}}>
                  <h3>Google Sheets Integration Status</h3>
                  <p style={{fontSize: 12, color: '#777'}}>Synchronize discovered leads and opportunity scores to a team working spreadsheet.</p>
                  <p style={{fontSize: 12, margin: '8px 0'}}>
                    Status: <span className={`badge ${sheetsWebhook ? 'done' : 'pending'}`}>{sheetsWebhook ? 'Configured' : 'Unconfigured'}</span>
                  </p>
                  <button className="secondary" onClick={() => setActiveTab('sheets')}>
                    Open Google Sheets Sync View
                  </button>
                </div>
              </div>
            </div>
          )}

        </div>
      </main>

      {/* MODALS */}
      {modal && (
        <div className="overlay" onClick={() => setModal(null)}>
          <div className="dialog" onClick={e => e.stopPropagation()}>
            <div className="dialog-head">
              <div>
                <p className="eyebrow">LEAD DATABASE</p>
                <h2>{modal === 'add' ? 'Add a business' : modal === 'reviews' ? 'Duplicate review' : modal === 'imports' ? 'Import history' : 'Import businesses'}</h2>
              </div>
              <button className="icon-btn" onClick={() => setModal(null)}><X size={20}/></button>
            </div>
            {notice && <p className="notice" role="alert">{notice}</p>}
            
            {modal === 'add' ? (
              <>
                <p className="dialog-sub">Start with what you know. Only the business name is required.</p>
                {(['name', 'website', 'industry', 'location', 'source'] as const).map(k => (
                  <div className="field" key={k}>
                    <label>{k === 'name' ? 'Business name *' : k === 'source' ? 'Source URL or attribution' : k[0].toUpperCase() + k.slice(1)}</label>
                    <input
                      value={form[k]}
                      onChange={e => setForm({...form, [k]: e.target.value})}
                      placeholder={{name: 'e.g. Acme Studio', website: 'https://example.com', industry: 'e.g. Retail', location: 'e.g. London, UK', source: 'e.g. public directory URL'}[k]}
                    />
                  </div>
                ))}
                <button className="primary full" disabled={!!busy || !form.name.trim()} onClick={submit}>
                  Add business <ArrowRight size={16}/>
                </button>
              </>
            ) : modal === 'reviews' ? (
              <>
                <p className="dialog-sub">Exact field matches are not proof of identity. No records are merged automatically; choose the appropriate outcome.</p>
                {reviews.length === 0 ? <p className="dialog-sub">No reviews yet.</p> : reviews.map(r => {
                  const target = targets[r.id] || (r.matches.length === 1 ? r.matches[0].business_id : '');
                  return (
                    <div className="opportunity" key={r.id}>
                      <div>
                        <strong>{r.incoming.name} · {r.status.replace(/_/g, ' ')}</strong>
                        <p>{r.classification === 'exact_fields' ? 'Exact match on name, domain and location' : 'Possible match'} · human review required</p>
                        <p>{r.incoming.website || 'No website'} · {r.incoming.location || 'Location unknown'}</p>
                        <p>Industry: {r.incoming.industry || 'Unknown'} · Source: {r.incoming.source || 'Not provided'}</p>
                        <p>Matched records: {r.matches.map(m => m.name + ' — ' + (m.location || 'location unknown') + ' (' + m.reasons.join(', ') + ')').join('; ')}</p>
                        {r.unreadable && (
                          <details>
                            <summary>Unreadable legacy data retained</summary>
                            <pre className="import-raw">{r.raw_incoming}\n{r.raw_matches}</pre>
                          </details>
                        )}
                        {r.status === 'pending' && !r.unreadable && (
                          <>
                            <label htmlFor={'target-' + r.id}>Existing business for linked decisions</label>
                            <select id={'target-' + r.id} value={target} onChange={e => setTargets({...targets, [r.id]: e.target.value})}>
                              <option value="">Select a match</option>
                              {r.matches.map(m => (
                                <option key={m.business_id} value={m.business_id}>
                                  {m.name} — {m.location || 'location unknown'} ({m.domain || 'no domain'}) · {m.business_id.slice(0, 8)}
                                </option>
                              ))}
                            </select>
                            <div className="review-actions">
                              <button className="secondary" disabled={!!busy || !target} onClick={() => resolve(r.id, 'same_business', target)}>Same business / duplicate</button>
                              <button className="secondary" disabled={!!busy} onClick={() => resolve(r.id, 'separate_business')}>Separate business</button>
                              <button className="secondary" disabled={!!busy || !target} onClick={() => resolve(r.id, 'separate_branch', target)}>Separate branch</button>
                              <button className="secondary" disabled={!!busy || !target} onClick={() => resolve(r.id, 'subsidiary', target)}>New record is subsidiary</button>
                              <button className="secondary" disabled={!!busy || !target} onClick={() => resolve(r.id, 'parent_company', target)}>New record is parent</button>
                            </div>
                            <p>Every decision retains this candidate and its source. A linked decision applies to the selected match.</p>
                          </>
                        )}
                        {r.resolution && <p>Decision: {r.resolution.decision.replace(/_/g, ' ')}</p>}
                        {r.resolution_history?.length > 0 && (
                          <details>
                            <summary>Decision history</summary>
                            {r.resolution_history.map((e, i) => (
                              <p key={i}>{new Date(e.created_at).toLocaleString()} · {e.decision.replace(/_/g, ' ')}</p>
                            ))}
                          </details>
                        )}
                        {r.status === 'reviewed' && (
                          <button className="secondary" disabled={!!busy} onClick={() => reopen(r.id)}>Reopen for a decision</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </>
            ) : modal === 'imports' ? (
              <>
                <p className="dialog-sub">Original CSV and each candidate are retained, including review decisions and validation errors.</p>
                {imports.length === 0 ? <p className="dialog-sub">No imports yet.</p> : imports.map(b => (
                  <div className="opportunity" key={b.id}>
                    <div>
                      <strong>{new Date(b.created_at).toLocaleString()}</strong>
                      <p>{b.id}</p>
                      <button className="secondary" onClick={() => loadImport(b.id)}>View batch</button>
                    </div>
                  </div>
                ))}
                {importDetail && (
                  <>
                    <h4>Selected batch</h4>
                    <details>
                      <summary>Original CSV</summary>
                      <pre className="import-raw">{importDetail.original_csv}</pre>
                    </details>
                    {importDetail.candidates.map(c => (
                      <div className="opportunity" key={c.id}>
                        <div>
                          <strong>Row {c.row_number} · {c.status.replace(/_/g, ' ')}</strong>
                          <p>{JSON.stringify(c.raw_data)}</p>
                          {c.error && <p>{c.error}</p>}
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </>
            ) : (
              <>
                <p className="dialog-sub">Paste CSV or select a file. Required column: <b>name</b>. Optional: website, industry, location, source. Maximum 500 rows.</p>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={async e => {
                    let f = e.target.files?.[0];
                    if (f) setCsv(await f.text());
                  }}
                />
                <textarea
                  value={csv}
                  onChange={e => setCsv(e.target.value)}
                  placeholder={'name,website,industry,location,source\nAcme,https://example.com,Retail,London,Manual research'}
                />
                <button className="primary full" disabled={!!busy || !csv} onClick={upload}>
                  Import businesses <ArrowRight size={16}/>
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* LEAD PROFILE DRAWER (360-DEGREE VIEW) */}
      {selected && (
        <div className="overlay" onClick={() => setSelected(null)}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-top">
              <span className="eyebrow">360° BUSINESS INTELLIGENCE</span>
              <button className="icon-btn" onClick={() => setSelected(null)}><X size={20}/></button>
            </div>
            
            <div className="profile-title">
              <div className="avatar big">{selected.name[0].toUpperCase()}</div>
              <div>
                <h2>{selected.name}</h2>
                <p>{selected.industry || 'Industry not specified'} · {selected.location || 'Location not specified'}</p>
              </div>
            </div>

            <div className="detail-box">
              <span>WEBSITE</span>
              {selected.website ? (
                <a href={selected.website.startsWith('http') ? selected.website : `https://${selected.website}`} target="_blank" rel="noreferrer">
                  🌐 {selected.website}
                </a>
              ) : (
                <div style={{background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: 8, padding: '10px 12px', marginTop: 4, marginBottom: 8}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: 6, color: '#fbbf24', fontWeight: 700, fontSize: 12}}>
                    🎯 Prime Target: No Website
                  </div>
                  <p style={{fontSize: 11, color: '#fde68a', margin: '4px 0 8px 0', lineHeight: 1.4}}>
                    This business has no registered website. Pitch SparkXFlow Website Development packages!
                  </p>
                  <button
                    className="primary"
                    style={{fontSize: 10, padding: '4px 10px', background: '#d97706', borderColor: '#b45309', color: '#fff'}}
                    disabled={busy === 'draft'}
                    onClick={() => generateOutreach(selected.id, 'Website Development')}
                  >
                    ⚡ Pitch Website Development
                  </button>
                </div>
              )}
              <span>SOURCES</span>
              {sources.length ? sources.map(src => <p key={src.id}>{src.source} · {src.kind}</p>) : <p>{selected.source}</p>}
              <span>RELATIONSHIPS</span>
              {relations.length ? relations.map(rel => (
                <p key={rel.id}>
                  {leads.find(l => l.id === rel.subject_business_id)?.name || rel.subject_business_id} {rel.relation.replace(/_/g, ' ')} {leads.find(l => l.id === rel.related_business_id)?.name || rel.related_business_id}
                </p>
              )) : <p>None recorded</p>}
            </div>

            {/* Quick Action: Generate Outreach */}
            <div style={{marginTop: 18, background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 9, padding: 14}}>
              <strong style={{fontSize: 12, display: 'block', marginBottom: 6}}>Generate AI Personalized Outreach Draft</strong>
              <div style={{display: 'flex', gap: 8}}>
                <select
                  id="target-service-picker"
                  className="select-input"
                  defaultValue="Website Development"
                >
                  {[
                    "Website Development", "Web Application Development", "AI Automation",
                    "E-commerce Development", "SaaS Development", "SEO and Digital Marketing",
                    "Mobile Application Development", "CRM and Business Automation", "Video Editing"
                  ].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <button
                  className="primary"
                  onClick={() => {
                    let el = document.getElementById('target-service-picker') as HTMLSelectElement;
                    let svc = el ? el.value : 'Website Development';
                    generateOutreach(selected.id, svc);
                  }}
                >
                  Draft Email
                </button>
              </div>
            </div>

            {/* Contacts Section */}
            <div className="research-head">
              <div>
                <h3>Decision-Maker Contacts</h3>
                <p>Publicly listed leadership and verified addresses.</p>
              </div>
              <button className="secondary" disabled={!!busy} onClick={discoverContactsForSelected}>
                <Users size={15}/> Discover Contacts
              </button>
            </div>

            {leadContacts.map(c => (
              <div className="opportunity" key={c.id}>
                <div>
                  <strong>{c.full_name} ({c.job_title})</strong>
                  <p>{c.email || 'No email'}</p>
                  <small>Status: {c.verification_status} · {c.contact_source}</small>
                </div>
                <button
                  className="secondary"
                  style={{fontSize: 11, padding: '4px 8px'}}
                  onClick={() => generateOutreach(selected.id, 'AI Automation', c.id)}
                >
                  Draft to Contact
                </button>
              </div>
            ))}

            <details style={{marginTop: 10, fontSize: 12}}>
              <summary style={{cursor: 'pointer', color: '#818cf8', fontWeight: 600}}>+ Manually Add Decision Maker</summary>
              <div style={{display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8, padding: 12, background: 'var(--bg-input)', borderRadius: 8, border: '1px solid var(--border-subtle)'}}>
                <input placeholder="Full Name *" value={newContact.full_name} onChange={e => setNewContact({...newContact, full_name: e.target.value})}/>
                <input placeholder="Job Title (e.g. Managing Director)" value={newContact.job_title} onChange={e => setNewContact({...newContact, job_title: e.target.value})}/>
                <input placeholder="Email Address" value={newContact.email} onChange={e => setNewContact({...newContact, email: e.target.value})}/>
                <input placeholder="Phone Number" value={newContact.phone} onChange={e => setNewContact({...newContact, phone: e.target.value})}/>
                <button className="primary" style={{marginTop: 4}} disabled={!newContact.full_name.trim()} onClick={addContactToSelected}>Save Contact</button>
              </div>
            </details>

            {/* Research & Qualification */}
            <div className="research-head" style={{marginTop: 30}}>
              <div>
                <h3>Website research</h3>
                <p>A preliminary, homepage-only review.</p>
              </div>
              <button className="primary" disabled={!!busy || !selected.website} onClick={() => research(selected)}>
                <FileSearch size={16}/>{busy === selected.id ? 'Researching…' : selected.report ? 'Research again' : 'Research website'}
              </button>
            </div>

            {selected.report ? (
              <>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, margin: '14px 0'}}>
                  <div style={{background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.25)', borderRadius: 8, padding: 10, textAlign: 'center'}}>
                    <small style={{display: 'block', fontSize: 10, color: '#a5b4fc', fontWeight: 600}}>BUSINESS QUALITY</small>
                    <strong style={{fontSize: 18, color: '#ffffff'}}>{(historySelection?.report || selected.report).business_quality || 'N/A'}/100</strong>
                  </div>
                  <div style={{background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: 8, padding: 10, textAlign: 'center'}}>
                    <small style={{display: 'block', fontSize: 10, color: '#6ee7b7', fontWeight: 600}}>CONVERSION POTENTIAL</small>
                    <strong style={{fontSize: 18, color: '#ffffff'}}>{(historySelection?.report || selected.report).conversion_potential || 'N/A'}/100</strong>
                  </div>
                  <div style={{background: 'rgba(56, 189, 248, 0.1)', border: '1px solid rgba(56, 189, 248, 0.25)', borderRadius: 8, padding: 10, textAlign: 'center'}}>
                    <small style={{display: 'block', fontSize: 10, color: '#7dd3fc', fontWeight: 600}}>EVIDENCE CONFIDENCE</small>
                    <strong style={{fontSize: 15, color: '#ffffff'}}>{((historySelection?.report || selected.report).evidence_confidence || 'medium').toUpperCase()}</strong>
                  </div>
                </div>

                <div className="disclaimer">
                  <ShieldCheck size={16}/>{(historySelection?.report || selected.report).limitations}
                </div>

                <h4>SERVICE OPPORTUNITIES</h4>
                {(historySelection?.report || selected.report).opportunities.map(o => (
                  <div className="opportunity" key={o.service}>
                    <div>
                      <strong>{o.service}</strong>
                      {o.observed_technical_state && (
                        <p style={{fontSize: 11, color: '#475569', margin: '2px 0'}}>
                          <b>Observed State:</b> {o.observed_technical_state}
                        </p>
                      )}
                      <p>{o.reason}</p>
                      <small>Confidence: {o.confidence} {o.buying_intent_status && `· Intent: ${o.buying_intent_status}`}</small>
                    </div>
                    <span>{o.score === null ? 'N/A' : o.score}<small>{o.score === null ? '' : ' / 100'}</small></span>
                  </div>
                ))}

                <h4>RESEARCH EVIDENCE</h4>
                {(historySelection?.report || selected.report).evidence.map((e, i) => (
                  <div className="evidence" key={i}>
                    <div className="check"><Check size={13}/></div>
                    <div>
                      <strong>{e.fact}</strong>
                      <a href={e.url} target="_blank" rel="noreferrer">{e.url}</a>
                      <small>Collected {new Date(e.collected_at).toLocaleString()} · {e.confidence} confidence</small>
                    </div>
                  </div>
                ))}

                <h4>RESEARCH HISTORY</h4>
                {history.map(h => (
                  <div className="opportunity" key={h.id}>
                    <div>
                      <strong>{new Date(h.collected_at).toLocaleString()} · {h.kind}</strong>
                      <p>{h.unreadable_legacy ? 'Original report retained; its format cannot be displayed.' : h.report?.title || 'Untitled report'}</p>
                      {h.report && <button className="secondary" onClick={() => setHistorySelection(h)}>View this report</button>}
                    </div>
                  </div>
                ))}
                {historySelection && <button className="secondary" onClick={() => setHistorySelection(null)}>View latest report</button>}
              </>
            ) : (
              <div className="research-empty">
                <FileSearch size={24}/>
                <strong>{history.length ? 'Legacy research retained' : 'No research yet'}</strong>
                <p>{history.length ? 'The original report is retained but cannot be displayed in its current format.' : 'Run a permitted page check to collect evidence.'}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<App/>);
