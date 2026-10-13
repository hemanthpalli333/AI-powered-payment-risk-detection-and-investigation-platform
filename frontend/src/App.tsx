import React, { useState, useEffect } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell 
} from 'recharts';
import { 
  LayoutDashboard, RefreshCw, AlertTriangle, Activity, MessageSquare, 
  Upload, Database, AlertCircle, CheckCircle2, HelpCircle, ShieldAlert
} from 'lucide-react';

// API Base URL
const API_URL = import.meta.env.VITE_API_URL || '/api/v1';

export default function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'reconciliation' | 'exceptions' | 'monitoring' | 'copilot'>('dashboard');
  
  // Dashboard State
  const [kpis, setKpis] = useState({
    total_records: 0,
    total_payments: 0,
    reconciled: 0,
    pending: 0,
    unmatched: 0,
    exceptions: 0,
    exception_value: 0.0,
    reconciliation_rate: 0.0,
    auto_match_rate: 0.0
  });
  const [statusDist, setStatusDist] = useState<any[]>([]);
  const [excBreakdown, setExcBreakdown] = useState<any[]>([]);
  const [dailyTrend, setDailyTrend] = useState<any[]>([]);
  
  // Reconciliation Screen State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadType, setUploadType] = useState<'payments' | 'bank-statements' | 'invoices' | 'settlements'>('payments');
  const [reconRunning, setReconRunning] = useState(false);
  const [reconMessage, setReconMessage] = useState('');
  
  // Exceptions Screen State
  const [exceptions, setExceptions] = useState<any[]>([]);
  const [selectedException, setSelectedException] = useState<any | null>(null);
  const [aiInvestigation, setAiInvestigation] = useState<any | null>(null);
  const [investigating, setInvestigating] = useState(false);
  const [decision, setDecision] = useState<'CONFIRM_MATCH' | 'MARK_EXCEPTION' | 'ESCALATE'>('CONFIRM_MATCH');
  const [comments, setComments] = useState('');
  const [decisionSubmitting, setDecisionSubmitting] = useState(false);
  
  // Monitoring Screen State
  const [dqReport, setDqReport] = useState<any | null>(null);
  const [driftStatus, setDriftStatus] = useState<string>('REVIEW_REQUIRED');
  const [driftDetails, setDriftDetails] = useState<any>({});
  
  // Copilot Screen State
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotChat, setCopilotChat] = useState<any[]>([]);
  const [copilotData, setCopilotData] = useState<any[] | null>(null);

  // Common notification alert
  const [alert, setAlert] = useState<{type: 'success' | 'error', message: string} | null>(null);

  const showAlert = (type: 'success' | 'error', message: string) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  };

  // Fetch Dashboard data
  const fetchDashboardData = async () => {
    try {
      const res = await fetch(`${API_URL}/dashboard/metrics`);
      if (!res.ok) throw new Error('Failed to load dashboard metrics');
      const data = await res.json();
      
      setKpis(data.kpis);
      
      // Format status distribution for pie chart
      const dist = [
        { name: 'Reconciled', value: data.status_distribution.reconciled, color: '#10B981' },
        { name: 'Exceptions', value: data.status_distribution.exceptions, color: '#EF4444' },
        { name: 'Pending', value: data.status_distribution.pending, color: '#F59E0B' },
        { name: 'Unmatched', value: data.status_distribution.unmatched, color: '#6B7280' },
      ].filter(item => item.value > 0);
      setStatusDist(dist);
      
      setExcBreakdown(data.exception_breakdown);
      setDailyTrend(data.daily_trend);
    } catch (e: any) {
      console.error(e);
      showAlert('error', e.message);
    }
  };

  // Fetch Exceptions List
  const fetchExceptions = async () => {
    try {
      const res = await fetch(`${API_URL}/exceptions`);
      if (!res.ok) throw new Error('Failed to fetch exception queue');
      const data = await res.json();
      setExceptions(data);
    } catch (e: any) {
      console.error(e);
      showAlert('error', e.message);
    }
  };

  // Fetch Monitoring metrics
  const fetchMonitoringData = async () => {
    try {
      const res = await fetch(`${API_URL}/monitoring`);
      if (!res.ok) throw new Error('Failed to load monitoring logs');
      const data = await res.json();
      setDqReport(data.data_quality);
      setDriftStatus(data.drift_status);
      setDriftDetails(data.drift_details);
    } catch (e: any) {
      console.error(e);
      showAlert('error', e.message);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    fetchExceptions();
    fetchMonitoringData();
  }, []);

  // Handle CSV Ingestion
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      showAlert('error', 'Select a file first');
      return;
    }
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    try {
      const res = await fetch(`${API_URL}/ingestion/${uploadType}`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
      const data = await res.json();
      
      if (data.inserted_count > 0) {
        showAlert('success', `Ingested ${data.inserted_count} records successfully!`);
      } else {
        showAlert('error', `Ingestion failed. Errors: ${JSON.stringify(data.errors)}`);
      }
      setSelectedFile(null);
      fetchDashboardData();
      fetchMonitoringData();
    } catch (e: any) {
      console.error(e);
      showAlert('error', e.message);
    }
  };

  // Execute Reconciliation Engine
  const runReconciliation = async () => {
    setReconRunning(true);
    setReconMessage('Reconciling payment ledgers...');
    try {
      const res = await fetch(`${API_URL}/reconciliation/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (!res.ok) throw new Error('Engine run failed');
      const data = await res.json();
      
      setReconMessage(`Reconciliation finished! Auto-reconciled: ${data.auto_matched}, Exceptions raised: ${data.exceptions_detected}. Time taken: ${data.execution_time_seconds}s.`);
      fetchDashboardData();
      fetchExceptions();
      fetchMonitoringData();
    } catch (e: any) {
      console.error(e);
      setReconMessage(`Engine execution errored: ${e.message}`);
      showAlert('error', e.message);
    } finally {
      setReconRunning(false);
    }
  };

  // Trigger AI Forensic Agent
  const triggerInvestigation = async (excId: number) => {
    setInvestigating(true);
    setAiInvestigation(null);
    try {
      const res = await fetch(`${API_URL}/investigation/${excId}`, { method: 'POST' });
      if (!res.ok) throw new Error('AI analysis failed');
      const data = await res.json();
      setAiInvestigation(data);
    } catch (e: any) {
      console.error(e);
      showAlert('error', e.message);
    } finally {
      setInvestigating(false);
    }
  };

  // Submit Human Controller Decision
  const submitDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedException) return;
    
    setDecisionSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/decisions/${selectedException.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reviewer_id: 'finance_admin_1',
          decision,
          comments
        })
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to submit decision');
      }
      
      showAlert('success', `Discrepancy resolved as ${decision}`);
      setSelectedException(null);
      setAiInvestigation(null);
      setComments('');
      fetchExceptions();
      fetchDashboardData();
    } catch (e: any) {
      console.error(e);
      showAlert('error', e.message);
    } finally {
      setDecisionSubmitting(false);
    }
  };

  // Submit Copilot NL Query
  const submitCopilotQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!copilotQuery.trim()) return;
    
    const userMsg = copilotQuery;
    setCopilotQuery('');
    setCopilotLoading(true);
    
    setCopilotChat(prev => [...prev, { sender: 'user', text: userMsg }]);
    
    try {
      const res = await fetch(`${API_URL}/copilot/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userMsg })
      });
      if (!res.ok) throw new Error('Copilot query error');
      const data = await res.json();
      
      setCopilotChat(prev => [...prev, { sender: 'copilot', text: data.answer }]);
      setCopilotData(data.query_results);
    } catch (e: any) {
      console.error(e);
      setCopilotChat(prev => [...prev, { sender: 'copilot', text: `Failed to execute: ${e.message}` }]);
    } finally {
      setCopilotLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-100 font-sans overflow-hidden">
      
      {/* Sidebar Navigation */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col justify-between">
        <div>
          <div className="p-6 flex items-center gap-3 border-b border-slate-800">
            <ShieldAlert className="w-8 h-8 text-indigo-400" />
            <span className="text-xl font-bold tracking-wider">ReconAI</span>
          </div>
          
          <nav className="p-4 space-y-2">
            <button 
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center w-full gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'dashboard' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-slate-800 hover:text-white'}`}
            >
              <LayoutDashboard className="w-5 h-5" />
              <span>Dashboard</span>
            </button>
            <button 
              onClick={() => { setActiveTab('reconciliation'); }}
              className={`flex items-center w-full gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'reconciliation' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-slate-800 hover:text-white'}`}
            >
              <RefreshCw className="w-5 h-5" />
              <span>Reconcile Queue</span>
            </button>
            <button 
              onClick={() => { setActiveTab('exceptions'); fetchExceptions(); }}
              className={`flex items-center w-full gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'exceptions' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-slate-800 hover:text-white'}`}
            >
              <AlertTriangle className="w-5 h-5" />
              <span>Exceptions Review</span>
            </button>
            <button 
              onClick={() => { setActiveTab('monitoring'); fetchMonitoringData(); }}
              className={`flex items-center w-full gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'monitoring' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-slate-800 hover:text-white'}`}
            >
              <Activity className="w-5 h-5" />
              <span>Monitoring & Drift</span>
            </button>
            <button 
              onClick={() => setActiveTab('copilot')}
              className={`flex items-center w-full gap-3 px-4 py-3 rounded-lg transition-colors ${activeTab === 'copilot' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-slate-800 hover:text-white'}`}
            >
              <MessageSquare className="w-5 h-5" />
              <span>AI Copilot</span>
            </button>
          </nav>
        </div>
        
        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-slate-800 flex items-center justify-center font-bold text-indigo-400">FC</div>
            <div>
              <p className="text-sm font-semibold">Finance Controller</p>
              <p className="text-xs text-gray-500">Tier 1 Auditor</p>
            </div>
          </div>
        </div>
      </aside>
      
      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        
        {/* Header */}
        <header className="h-16 bg-white border-b border-gray-200 px-8 flex items-center justify-between z-10">
          <h2 className="text-lg font-bold text-gray-800 capitalize">{activeTab} Operational Portal</h2>
          
          <div className="flex items-center gap-4">
            <button 
              onClick={() => { fetchDashboardData(); fetchExceptions(); fetchMonitoringData(); }}
              className="text-gray-500 hover:text-indigo-600 p-2 hover:bg-gray-100 rounded-full transition-colors"
              title="Sync metrics"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
            <span className="text-sm text-gray-500">Server: <b className="text-green-600 font-semibold">Online</b></span>
          </div>
        </header>
        
        {/* Alert Notification banner */}
        {alert && (
          <div className={`p-4 text-sm font-medium ${alert.type === 'success' ? 'bg-green-50 text-green-800 border-b border-green-200' : 'bg-red-50 text-red-800 border-b border-red-200'} flex items-center gap-2`}>
            {alert.type === 'success' ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
            {alert.message}
          </div>
        )}
        
        {/* View Layout Router */}
        <div className="flex-1 overflow-auto p-8">
          
          {/* TAB 1: DASHBOARD VIEW */}
          {activeTab === 'dashboard' && (
            <div className="space-y-8">
              
              {/* KPI Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500 font-medium">Total Ledgers</p>
                    <p className="text-2xl font-extrabold text-slate-800 mt-1">{kpis.total_records}</p>
                  </div>
                  <Database className="w-10 h-10 text-indigo-400" />
                </div>
                
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500 font-medium">Auto-Reconciled</p>
                    <p className="text-2xl font-extrabold text-green-600 mt-1">{kpis.reconciled}</p>
                    <p className="text-xs text-gray-400 mt-1">Recon rate: {kpis.reconciliation_rate}%</p>
                  </div>
                  <CheckCircle2 className="w-10 h-10 text-green-400" />
                </div>
                
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500 font-medium">Pending Review</p>
                    <p className="text-2xl font-extrabold text-amber-500 mt-1">{kpis.pending}</p>
                  </div>
                  <HelpCircle className="w-10 h-10 text-amber-400" />
                </div>
                
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500 font-medium">Unresolved Exception Val</p>
                    <p className="text-2xl font-extrabold text-red-600 mt-1">₹{kpis.exception_value.toLocaleString()}</p>
                    <p className="text-xs text-gray-400 mt-1">Total exceptions: {kpis.exceptions}</p>
                  </div>
                  <AlertTriangle className="w-10 h-10 text-red-400" />
                </div>
              </div>
              
              {/* Charts grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                
                {/* 1. Reconciliation Rates & Trend */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                  <h3 className="text-base font-bold text-gray-800 mb-6">Daily Reconciliation Rate Trend</h3>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={dailyTrend}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="reconciled_count" name="Reconciled Transactions" stroke="#4F46E5" strokeWidth={3} activeDot={{ r: 8 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                
                {/* 2. Exception Types Pie Chart & Breakdown */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                  <h3 className="text-base font-bold text-gray-800 mb-6">Exception Distribution (Outstanding)</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    
                    {/* Pie Chart */}
                    <div className="h-60 flex items-center justify-center">
                      {statusDist.length === 0 ? (
                        <p className="text-gray-400 text-sm">No transaction records present.</p>
                      ) : (
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={statusDist}
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={80}
                              paddingAngle={5}
                              dataKey="value"
                            >
                              {statusDist.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip />
                          </PieChart>
                        </ResponsiveContainer>
                      )}
                    </div>
                    
                    {/* Legend table */}
                    <div className="flex flex-col justify-center space-y-4">
                      {statusDist.map((item, idx) => (
                        <div key={idx} className="flex items-center justify-between border-b pb-2 border-gray-100">
                          <div className="flex items-center gap-2">
                            <span className="w-3 h-3 rounded-full" style={{backgroundColor: item.color}} />
                            <span className="text-sm text-gray-600 font-medium">{item.name}</span>
                          </div>
                          <span className="text-sm font-bold text-gray-800">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Detailed Exception Types Breakdown Table */}
              <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                <h3 className="text-base font-bold text-gray-800 mb-6">Outstanding Exceptions Breakdown</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-gray-200 text-gray-400 text-xs font-semibold uppercase tracking-wider">
                        <th className="pb-3">Exception Category</th>
                        <th className="pb-3 text-center">Unresolved Count</th>
                        <th className="pb-3 text-right">Aggregated Outstanding Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {excBreakdown.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="py-6 text-center text-gray-400 text-sm">No exceptions outstanding. Excellent reconciliation status!</td>
                        </tr>
                      ) : (
                        excBreakdown.map((row, idx) => (
                          <tr key={idx} className="text-sm font-medium hover:bg-gray-50 transition-colors">
                            <td className="py-3 text-gray-800">{row.type.replace('_', ' ')}</td>
                            <td className="py-3 text-center text-amber-500 font-bold">{row.count}</td>
                            <td className="py-3 text-right text-gray-900 font-extrabold">₹{row.value.toLocaleString()}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
          
          {/* TAB 2: RECONCILIATION VIEW */}
          {activeTab === 'reconciliation' && (
            <div className="space-y-8">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                
                {/* 1. CSV File Ingestion Panel */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm col-span-1">
                  <h3 className="text-base font-bold text-gray-800 mb-6">Ingest Financial Datasets</h3>
                  
                  <form onSubmit={handleUpload} className="space-y-6">
                    <div>
                      <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Dataset Target</label>
                      <select 
                        value={uploadType} 
                        onChange={(e) => setUploadType(e.target.value as any)}
                        className="w-full border border-gray-200 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-600 bg-white"
                      >
                        <option value="payments">Payments Transactions (payments.csv)</option>
                        <option value="bank-statements">Bank Statements (bank.csv)</option>
                        <option value="invoices">Invoices Ledger (invoices.csv)</option>
                        <option value="settlements">Processor Settlements (settlements.csv)</option>
                      </select>
                    </div>
                    
                    <div>
                      <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Upload File (.csv)</label>
                      <div className="border-2 border-dashed border-gray-200 hover:border-indigo-600 rounded-lg p-6 flex flex-col items-center justify-center transition-colors cursor-pointer relative bg-slate-50">
                        <Upload className="w-8 h-8 text-gray-400 mb-2" />
                        <span className="text-xs text-gray-500 text-center font-medium">
                          {selectedFile ? selectedFile.name : 'Click to select / drop CSV file'}
                        </span>
                        <input 
                          type="file" 
                          accept=".csv"
                          onChange={(e) => e.target.files && setSelectedFile(e.target.files[0])}
                          className="absolute inset-0 opacity-0 cursor-pointer"
                        />
                      </div>
                    </div>
                    
                    <button 
                      type="submit"
                      disabled={!selectedFile}
                      className="w-full bg-slate-900 text-white rounded-lg p-3 text-sm font-semibold hover:bg-slate-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      <Database className="w-4 h-4" />
                      <span>Ingest Records</span>
                    </button>
                  </form>
                </div>
                
                {/* 2. Run Reconciliation Engine */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm col-span-2 flex flex-col justify-between">
                  <div>
                    <h3 className="text-base font-bold text-gray-800 mb-4">Run Reconciler Engine</h3>
                    <p className="text-sm text-gray-500 leading-relaxed mb-6">
                      ReconAI operates a multi-layered verification system. Running reconciliation will execute Level 1 (Exact matching), Level 2 (Weighted rule matching), Level 3 (Fuzzy reference matching), and Level 4 (Machine Learning evaluation) sequentially. High-confidence pairs clear immediately. Potential discrepancies generate auditable Exception entries for review.
                    </p>
                    
                    {reconMessage && (
                      <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 whitespace-pre-line leading-relaxed mb-6">
                        {reconMessage}
                      </div>
                    )}
                  </div>
                  
                  <button 
                    onClick={runReconciliation}
                    disabled={reconRunning}
                    className="w-full bg-indigo-600 text-white rounded-lg p-4 font-bold text-base hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 shadow-sm"
                  >
                    <RefreshCw className={`w-5 h-5 ${reconRunning ? 'animate-spin' : ''}`} />
                    <span>{reconRunning ? 'Processing Transactions...' : 'Start Matching Reconciliation'}</span>
                  </button>
                </div>
              </div>
            </div>
          )}
          
          {/* TAB 3: EXCEPTIONS REVIEW QUEUE & AI FORENSICS */}
          {activeTab === 'exceptions' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
              
              {/* Left Column: List of Exceptions */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="p-6 border-b border-gray-100 flex items-center justify-between">
                  <h3 className="text-base font-bold text-gray-800">Operational Exception Queue</h3>
                  <span className="px-3 py-1 bg-amber-50 text-amber-600 text-xs font-bold rounded-full">
                    {exceptions.length} Outstanding
                  </span>
                </div>
                
                <div className="divide-y divide-gray-100 max-h-[600px] overflow-auto">
                  {exceptions.length === 0 ? (
                    <div className="p-12 text-center text-gray-400 text-sm">No exceptions logged in database.</div>
                  ) : (
                    exceptions.map((exc) => (
                      <div 
                        key={exc.id} 
                        onClick={() => { setSelectedException(exc); setAiInvestigation(null); }}
                        className={`p-6 hover:bg-gray-50 transition-colors cursor-pointer flex justify-between items-start ${selectedException?.id === exc.id ? 'bg-indigo-50/50 border-l-4 border-indigo-600' : ''}`}
                      >
                        <div className="space-y-1">
                          <p className="text-xs font-semibold text-gray-400 uppercase">{exc.exception_type.replace('_', ' ')}</p>
                          <p className="text-sm font-bold text-slate-800">{exc.transaction_id}</p>
                          <p className="text-xs text-gray-500">Logged: {new Date(exc.created_at).toLocaleString()}</p>
                        </div>
                        <div className="text-right space-y-2">
                          <p className="text-sm font-extrabold text-red-600">₹{exc.difference_amount.toLocaleString()}</p>
                          <span className={`px-2.5 py-0.5 text-xs font-semibold rounded-full uppercase ${
                            exc.status === 'PENDING' ? 'bg-amber-100 text-amber-700' :
                            exc.status === 'INVESTIGATING' ? 'bg-blue-100 text-blue-700' :
                            exc.status === 'ESCALATED' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                          }`}>
                            {exc.status}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              
              {/* Right Column: AI Forensic Auditor & Human Decision Form */}
              <div className="space-y-8">
                {selectedException ? (
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-6">
                    
                    {/* Exception Header */}
                    <div className="border-b pb-4 border-gray-100 flex justify-between items-center">
                      <div>
                        <h4 className="text-lg font-bold text-gray-800">Discrepancy Details</h4>
                        <p className="text-xs text-gray-500 mt-1">Transaction Ref: <b>{selectedException.transaction_id}</b></p>
                      </div>
                      
                      <div className="text-right">
                        <p className="text-xs text-gray-400">Difference</p>
                        <p className="text-base font-extrabold text-red-600">₹{selectedException.difference_amount.toLocaleString()}</p>
                      </div>
                    </div>
                    
                    {/* Discrepancy Evidence JSON summaries */}
                    <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 text-xs leading-relaxed text-slate-700">
                      <h5 className="font-bold uppercase text-slate-500 text-[10px] tracking-wider mb-2">Ground Evidence Details</h5>
                      <p className="mb-2"><b>Audit Message:</b> {selectedException.evidence?.message || 'No direct summary mapped.'}</p>
                      {selectedException.evidence?.payment_amount && (
                        <p><b>Payment Amt:</b> ₹{selectedException.evidence.payment_amount} | <b>Invoice Amt:</b> ₹{selectedException.evidence.invoice_amount}</p>
                      )}
                      {selectedException.evidence?.duplicate_transaction_ids && (
                        <p><b>Duplicates Found:</b> {selectedException.evidence.duplicate_transaction_ids.join(', ')}</p>
                      )}
                      {selectedException.evidence?.settlement_gross && (
                        <div className="space-y-1 mt-1">
                          <p><b>Settlement Gross:</b> ₹{selectedException.evidence.settlement_gross} | <b>Fee:</b> ₹{selectedException.evidence.settlement_fee}</p>
                          <p><b>Expect Net:</b> ₹{selectedException.evidence.expected_net} | <b>Actual Net:</b> ₹{selectedException.evidence.settlement_net}</p>
                        </div>
                      )}
                    </div>
                    
                    {/* AI Investigator Section */}
                    <div className="border border-indigo-100 bg-indigo-50/20 rounded-xl p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ShieldAlert className="w-5 h-5 text-indigo-600" />
                          <h5 className="text-sm font-bold text-indigo-900">AI Investigation Agent</h5>
                        </div>
                        
                        {!aiInvestigation && (
                          <button 
                            onClick={() => triggerInvestigation(selectedException.id)}
                            disabled={investigating}
                            className="bg-indigo-600 text-white text-xs px-3 py-1.5 rounded-lg hover:bg-indigo-700 transition-colors font-semibold disabled:opacity-50 flex items-center gap-1.5"
                          >
                            <RefreshCw className={`w-3 h-3 ${investigating ? 'animate-spin' : ''}`} />
                            <span>Analyze Discrepancy</span>
                          </button>
                        )}
                      </div>
                      
                      {investigating && (
                        <div className="py-6 flex flex-col items-center justify-center gap-2 text-xs font-semibold text-indigo-600">
                          <RefreshCw className="w-5 h-5 animate-spin" />
                          <span>AI Auditor is querying transaction logs...</span>
                        </div>
                      )}
                      
                      {aiInvestigation && (
                        <div className="space-y-3 text-xs">
                          <div className="border-l-4 border-indigo-500 pl-3">
                            <p className="font-bold text-indigo-900">Case Diagnosis:</p>
                            <p className="text-gray-700 mt-1 leading-relaxed">{aiInvestigation.summary}</p>
                          </div>
                          
                          <div>
                            <p className="font-bold text-indigo-900">Possible Causes:</p>
                            <ul className="list-disc pl-4 space-y-1 text-gray-700 mt-1">
                              {aiInvestigation.possible_causes.map((c: string, i: number) => (
                                <li key={i}>{c}</li>
                              ))}
                            </ul>
                          </div>
                          
                          <div className="flex items-center gap-4 bg-white border border-indigo-100 p-3 rounded-lg justify-between mt-2">
                            <div>
                              <p className="text-indigo-900 font-bold uppercase text-[9px]">Recommended Resolution</p>
                              <p className="text-sm font-extrabold text-indigo-700 mt-0.5">{aiInvestigation.recommendation.replace('_', ' ')}</p>
                            </div>
                            <div className="text-right">
                              <p className="text-indigo-900 font-bold uppercase text-[9px]">Confidence</p>
                              <p className="text-sm font-extrabold text-indigo-700 mt-0.5">{Math.round(aiInvestigation.confidence * 100)}%</p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                    
                    {/* Human Auditor Review decision submission */}
                    <form onSubmit={submitDecision} className="space-y-4 pt-4 border-t border-gray-100">
                      <h5 className="text-sm font-bold text-gray-800">Resolve Exception Case</h5>
                      
                      <div className="grid grid-cols-3 gap-3">
                        <button
                          type="button"
                          onClick={() => setDecision('CONFIRM_MATCH')}
                          className={`p-2.5 rounded-lg border text-xs font-semibold text-center transition-colors ${decision === 'CONFIRM_MATCH' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'}`}
                        >
                          Confirm Match
                        </button>
                        <button
                          type="button"
                          onClick={() => setDecision('MARK_EXCEPTION')}
                          className={`p-2.5 rounded-lg border text-xs font-semibold text-center transition-colors ${decision === 'MARK_EXCEPTION' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'}`}
                        >
                          Mark Exception
                        </button>
                        <button
                          type="button"
                          onClick={() => setDecision('ESCALATE')}
                          className={`p-2.5 rounded-lg border text-xs font-semibold text-center transition-colors ${decision === 'ESCALATE' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'}`}
                        >
                          Escalate Case
                        </button>
                      </div>
                      
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Reviewer Audit Comments</label>
                        <textarea
                          rows={3}
                          value={comments}
                          onChange={(e) => setComments(e.target.value)}
                          placeholder="Provide details for why you are confirming/marking this exception..."
                          className="w-full border border-gray-200 rounded-lg p-3 text-xs focus:outline-none focus:border-indigo-600"
                          required
                        />
                      </div>
                      
                      <button
                        type="submit"
                        disabled={decisionSubmitting}
                        className="w-full bg-slate-900 text-white rounded-lg p-3 text-sm font-bold hover:bg-slate-800 transition-colors disabled:opacity-50"
                      >
                        {decisionSubmitting ? 'Persisting Decision...' : 'Persist Reconciliation Decision'}
                      </button>
                    </form>
                    
                  </div>
                ) : (
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center text-gray-400 flex flex-col items-center justify-center h-80">
                    <AlertTriangle className="w-12 h-12 mb-3 text-slate-300" />
                    <p className="text-sm font-semibold">Select an exception from the queue list to audit.</p>
                  </div>
                )}
              </div>
              
            </div>
          )}
          
          {/* TAB 4: MONITORING & DATA QUALITY */}
          {activeTab === 'monitoring' && (
            <div className="space-y-8">
              
              {/* Drift Summary cards */}
              <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-gray-800">Statistical Distribution Drift</h3>
                  <p className="text-xs text-gray-500 mt-1">Data drift compares the current transactions metrics dynamically with baseline profiles.</p>
                </div>
                
                <div className="flex items-center gap-3">
                  <span className={`px-4 py-2 font-black rounded-lg text-sm uppercase ${
                    driftStatus === 'HEALTHY' ? 'bg-green-100 text-green-700' :
                    driftStatus === 'DRIFT_DETECTED' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                  }`}>
                    {driftStatus.replace('_', ' ')}
                  </span>
                </div>
              </div>
              
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                
                {/* 1. Data Quality Monitor */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm col-span-1">
                  <h4 className="text-base font-bold text-gray-800 mb-6">Data Quality Report</h4>
                  
                  {dqReport ? (
                    <div className="space-y-5">
                      <div className="flex justify-between border-b pb-3 border-gray-100 text-sm">
                        <span className="text-gray-500 font-medium">Processed Elements</span>
                        <span className="font-extrabold text-gray-800">{dqReport.total_records}</span>
                      </div>
                      <div className="flex justify-between border-b pb-3 border-gray-100 text-sm">
                        <span className="text-gray-500 font-medium">Missing Value Fields</span>
                        <span className={`font-extrabold ${dqReport.missing_fields > 0 ? 'text-red-500' : 'text-green-600'}`}>{dqReport.missing_fields}</span>
                      </div>
                      <div className="flex justify-between border-b pb-3 border-gray-100 text-sm">
                        <span className="text-gray-500 font-medium">Duplicate Records</span>
                        <span className={`font-extrabold ${dqReport.duplicate_records > 0 ? 'text-red-500' : 'text-green-600'}`}>{dqReport.duplicate_records}</span>
                      </div>
                      <div className="flex justify-between border-b pb-3 border-gray-100 text-sm">
                        <span className="text-gray-500 font-medium">Invalid Amounts (&le; 0)</span>
                        <span className={`font-extrabold ${dqReport.invalid_amounts > 0 ? 'text-red-500' : 'text-green-600'}`}>{dqReport.invalid_amounts}</span>
                      </div>
                      <div className="flex justify-between border-b pb-3 border-gray-100 text-sm">
                        <span className="text-gray-500 font-medium">Invalid Dates</span>
                        <span className={`font-extrabold ${dqReport.invalid_dates > 0 ? 'text-red-500' : 'text-green-600'}`}>{dqReport.invalid_dates}</span>
                      </div>
                      <div className="flex justify-between pb-3 text-sm">
                        <span className="text-gray-500 font-medium">Currency Inconsistencies</span>
                        <span className={`font-extrabold ${dqReport.currency_inconsistencies > 0 ? 'text-red-500' : 'text-green-600'}`}>{dqReport.currency_inconsistencies}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-gray-400 text-xs py-8 text-center">No quality metrics computed.</p>
                  )}
                </div>
                
                {/* 2. Drift & Evidently Details */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm col-span-2">
                  <h4 className="text-base font-bold text-gray-800 mb-6">Drift Metric Engine details</h4>
                  
                  <div className="bg-slate-50 p-5 rounded-lg border border-slate-200 text-xs font-mono whitespace-pre-wrap leading-relaxed text-slate-700 h-60 overflow-auto">
                    {JSON.stringify(driftDetails, null, 2)}
                  </div>
                </div>
              </div>
              
            </div>
          )}
          
          {/* TAB 5: AI FINANCE COPILOT CHAT */}
          {activeTab === 'copilot' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
              
              {/* Chat Column */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 col-span-2 flex flex-col h-[550px]">
                <h3 className="text-base font-bold text-gray-800 mb-4 flex items-center gap-2">
                  <MessageSquare className="w-5 h-5 text-indigo-600" />
                  <span>Natural Language Assistant</span>
                </h3>
                
                {/* Chat window */}
                <div className="flex-1 overflow-auto space-y-4 mb-4 border border-gray-100 p-4 rounded-lg bg-slate-50/50">
                  {copilotChat.length === 0 && (
                    <div className="text-center text-gray-400 py-16 space-y-2">
                      <HelpCircle className="w-10 h-10 mx-auto text-gray-300" />
                      <p className="text-sm font-semibold">Ask me any question about the ledgers.</p>
                      <div className="flex flex-wrap justify-center gap-2 pt-4">
                        <button 
                          onClick={() => setCopilotQuery('Show unresolved exceptions above ₹5,000')}
                          className="bg-white text-[11px] text-gray-600 font-medium px-3 py-1.5 border rounded-lg hover:border-indigo-600 transition-colors"
                        >
                          "Exceptions above ₹5,000"
                        </button>
                        <button 
                          onClick={() => setCopilotQuery('Show duplicate-payment candidates')}
                          className="bg-white text-[11px] text-gray-600 font-medium px-3 py-1.5 border rounded-lg hover:border-indigo-600 transition-colors"
                        >
                          "Show duplicates"
                        </button>
                        <button 
                          onClick={() => setCopilotQuery('What is the current reconciliation rate?')}
                          className="bg-white text-[11px] text-gray-600 font-medium px-3 py-1.5 border rounded-lg hover:border-indigo-600 transition-colors"
                        >
                          "Reconciliation rate"
                        </button>
                      </div>
                    </div>
                  )}
                  
                  {copilotChat.map((msg, idx) => (
                    <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`p-3 max-w-lg rounded-xl text-xs leading-relaxed ${msg.sender === 'user' ? 'bg-indigo-600 text-white font-medium rounded-tr-none' : 'bg-white border border-gray-200 text-gray-800 rounded-tl-none shadow-sm'}`}>
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  
                  {copilotLoading && (
                    <div className="flex justify-start">
                      <div className="bg-white border border-gray-200 p-3 rounded-xl rounded-tl-none shadow-sm text-xs text-gray-500 flex items-center gap-2">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Querying backend databases...</span>
                      </div>
                    </div>
                  )}
                </div>
                
                <form onSubmit={submitCopilotQuery} className="flex gap-2">
                  <input
                    type="text"
                    value={copilotQuery}
                    onChange={(e) => setCopilotQuery(e.target.value)}
                    placeholder="E.g., Show unresolved exceptions above ₹10,000..."
                    className="flex-1 border border-gray-200 rounded-lg p-3 text-xs focus:outline-none focus:border-indigo-600"
                    disabled={copilotLoading}
                  />
                  <button
                    type="submit"
                    disabled={copilotLoading}
                    className="bg-slate-900 text-white font-bold text-xs px-6 py-3 rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
                  >
                    Send Query
                  </button>
                </form>
              </div>
              
              {/* Ground-truth Data Table Column */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 col-span-1 h-[550px] overflow-auto">
                <h4 className="text-sm font-bold text-gray-800 mb-4 uppercase tracking-wider text-slate-500">Query Ground-Truth Data</h4>
                
                {!copilotData ? (
                  <p className="text-gray-400 text-xs py-8 text-center">Results will be loaded when a query executes.</p>
                ) : copilotData.length === 0 ? (
                  <p className="text-gray-500 text-xs py-8 text-center font-medium">Empty set returned.</p>
                ) : (
                  <div className="space-y-4">
                    {copilotData.map((item, idx) => (
                      <div key={idx} className="border-b pb-3 border-gray-100 text-xs font-mono text-gray-700 leading-relaxed">
                        {Object.entries(item).map(([k, v]) => (
                          <div key={k} className="flex justify-between mt-1">
                            <span className="font-bold text-indigo-700">{k}:</span>
                            <span className="text-slate-800">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              
            </div>
          )}
          
        </div>
      </main>
      
    </div>
  );
}
