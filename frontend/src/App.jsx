import React, { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDown, ArrowRight, ArrowUpRight, Check, CheckCircle2, ChevronDown, ChevronRight, Circle, Clock3, Code2, Database, ExternalLink, GitBranch, Github, LayoutDashboard, Loader2, LockKeyhole, LogOut, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, Terminal, TriangleAlert, X, XCircle } from 'lucide-react';
import { cognito, diagnosisLabel, githubUrl, request, runStats, validateConfig } from './client.js';
import './styles.css';
import './theme.css';

const savedConfig = (() => { try { return JSON.parse(localStorage.getItem('deployiq.connection') || '{}'); } catch { return {}; } })();
const initialConfig = {apiUrl: import.meta.env.VITE_API_BASE_URL || savedConfig.apiUrl || '', clientId: import.meta.env.VITE_COGNITO_CLIENT_ID || savedConfig.clientId || ''};
const when = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? 'Not available' : d.toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}); };
const isFailed = run => ['failure', 'timed_out'].includes(run.conclusion);

function Brand({light=false}) {return <div className={`brand ${light?'light':''}`}><span className="brand-icon"><Activity size={23} strokeWidth={2.4}/></span><span>Deploy<span className="brand-iq">IQ</span></span></div>;}
function Badge({run}) {const good = run.conclusion === 'success'; const fail = isFailed(run); return <span className={`badge ${good?'good':fail?'bad':'neutral'}`}>{good?<CheckCircle2 size={13}/>:fail?<XCircle size={13}/>:<Circle size={12}/>} {good?'Passed':fail?'Failed':run.conclusion || 'Unknown'}</span>;}

function SignIn({config, setConfig, onSession, notice}) {
  const [draft, setDraft] = useState(config);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [challenge, setChallenge] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ready = validateConfig(config);
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      if (challenge && password !== confirm) throw new Error('The new passwords must match.');
      const result = challenge ? await cognito('RespondToAuthChallenge', {ClientId:config.clientId, ChallengeName:'NEW_PASSWORD_REQUIRED', Session:challenge.Session, ChallengeResponses:{USERNAME:challenge.username, NEW_PASSWORD:password}}) : await cognito('InitiateAuth', {ClientId:config.clientId, AuthFlow:'USER_PASSWORD_AUTH', AuthParameters:{USERNAME:username, PASSWORD:password}});
      if (result.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
        setChallenge({...result, username:result.ChallengeParameters?.USER_ID_FOR_SRP || username}); setPassword('');
      } else if (result.AuthenticationResult?.IdToken) {
        setPassword(''); setConfirm(''); onSession({token:result.AuthenticationResult.IdToken, username, expiresAt:Date.now() + result.AuthenticationResult.ExpiresIn*1000});
      } else throw new Error('This sign-in challenge is not supported. Contact your workspace administrator.');
    } catch(error) {setError(error.message || 'Unable to sign in.');}
    finally {setBusy(false);}
  }
  function saveConnection(event) {
    event.preventDefault(); setError('');
    const next = {apiUrl:draft.apiUrl.trim().replace(/\/$/, ''), clientId:draft.clientId.trim()};
    if (!validateConfig(next)) {setError('Enter the HTTPS API Gateway base URL in us-east-1 and your Cognito client ID.'); return;}
    localStorage.setItem('deployiq.connection', JSON.stringify(next)); setConfig(next);
  }
  return <main className="signin">
    <section className="signin-story"><Brand light/><div className="story-content"><span className="eyebrow">PIPELINE INTELLIGENCE</span><h1>Know what failed.<br/><em>Know what’s next.</em></h1><p>Your deployment history, failure evidence, and next steps. One clear view of the path from commit to release.</p><div className="story-flow">{[[Github,'GitHub Actions','Your workflow completes'],[Database,'DeployIQ monitoring','The result is recorded'],[Sparkles,'Failure diagnosis','Evidence becomes a next step']].map(([Icon,title,desc],i)=><React.Fragment key={title}>{i>0&&<span className="flow-line"/>}<div className="flow-item"><span><Icon size={20}/></span><div><strong>{title}</strong><small>{desc}</small></div><Check size={16}/></div></React.Fragment>)}</div></div><footer><ShieldCheck size={15}/> Private team workspace · AWS</footer></section>
    <section className="signin-form"><div className="login-box"><div className="login-mark"><LockKeyhole size={24}/></div><span className="eyebrow muted">YOUR WORKSPACE</span><h2>{challenge?'Set your password':'Welcome to DeployIQ'}</h2><p>{challenge?'Choose a permanent password to finish your first sign-in.':'Sign in to see how your pipelines are doing.'}</p>
      {notice&&<div className="notice" role="status">{notice}</div>}{error&&<div className="error" role="alert">{error}</div>}
      <form onSubmit={submit}>
        {!challenge&&<label>Username<input autoComplete="username" required value={username} onChange={e=>setUsername(e.target.value)} placeholder="Your team username"/></label>}
        <label>{challenge?'New password':'Password'}<input type="password" autoComplete={challenge?'new-password':'current-password'} required minLength={challenge?12:1} value={password} onChange={e=>setPassword(e.target.value)}/></label>
        {challenge&&<><label>Confirm new password<input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label><small>12+ characters, uppercase, lowercase, number, and symbol.</small></>}
        <button className="primary login-button" disabled={!ready||busy}>{busy?<Loader2 size={17} className="spin"/>:<ArrowRight size={17}/>} {busy?'Signing in…':challenge?'Set password and continue':'Sign in to workspace'}</button>
      </form>
      <p className="login-help">Accounts are created by your workspace administrator.</p>
      <details className="connection" open={!ready||undefined}><summary><Settings2 size={14}/> Connection settings <ChevronDown size={14}/></summary><form onSubmit={saveConnection}><p>Use the public connection values from your CloudFormation stack. No AWS access keys are needed.</p><label>Dashboard API URL<input type="url" required value={draft.apiUrl} onChange={e=>setDraft({...draft,apiUrl:e.target.value})} placeholder="https://….execute-api.us-east-1.amazonaws.com"/></label><label>Cognito client ID<input required value={draft.clientId} onChange={e=>setDraft({...draft,clientId:e.target.value})}/></label><button className="secondary">Save connection</button>{ready&&<small className="connected"><CheckCircle2 size={13}/> Connection configured</small>}</form></details>
    </div><span className="login-footnote">Credentials go directly to Amazon Cognito. Session tokens stay in memory.</span></section>
  </main>;
}

function Detail({run, busy, error, onClose}) {
  const link = githubUrl(run?.html_url);
  return <aside className="detail-panel" aria-label="Run details"><div className="panel-heading"><span><Terminal size={16}/> RUN DETAILS</span><button className="icon-button" onClick={onClose} aria-label="Close run details"><X size={17}/></button></div>
    {busy?<div className="detail-loading"><Loader2 className="spin" size={24}/> Loading run details…</div>:error?<div className="error" role="alert">{error}</div>:!run?<div className="detail-empty"><div className="empty-icon"><GitBranch size={26}/></div><h3>A closer look at every run</h3><p>Select a pipeline run to see its release details, failure evidence, and suggested next steps.</p></div>:<>
      <div className="detail-title"><Badge run={run}/><h2>{run.name || 'Workflow run'}</h2><p>Run #{run.run_id} <span>·</span> Attempt {run.run_attempt}</p></div>
      <dl className="metadata"><div><dt>Repository</dt><dd>{run.repository}</dd></div><div><dt>Branch</dt><dd><GitBranch size={13}/>{run.head_branch || '—'}</dd></div><div><dt>Commit</dt><dd><code>{run.head_sha?.slice(0,12)||'—'}</code></dd></div><div><dt>Recorded</dt><dd>{when(run.received_at)}</dd></div></dl>
      <section className="diagnosis"><div className="section-label"><Sparkles size={16}/><h3>Failure diagnosis</h3>{run.analysis_source&&<span className={`source ${run.analysis_source==='bedrock'?'ai':''}`}>{diagnosisLabel(run)}</span>}</div>
        {!isFailed(run)?<div className="success-note"><CheckCircle2 size={20}/><div><strong>No failure to investigate</strong><p>This run did not require failure analysis.</p></div></div>:run.diagnosis?<>
          {run.analysis_source==='rules'&&<div className="rules-note"><ShieldCheck size={15}/><span>Rules-based finding. {run.ai_error_code==='ThrottlingException'?'Bedrock is currently quota-limited.':'AI analysis was unavailable for this run.'}</span></div>}
          <h4>Likely cause</h4><p>{run.diagnosis.root_cause}</p><h4>Evidence from the logs</h4>{run.diagnosis.evidence?.length?<div className="evidence">{run.diagnosis.evidence.map((quote,i)=><pre key={i}>{quote}</pre>)}</div>:<p>No specific evidence was identified.</p>}<h4>Suggested fix</h4><p>{run.diagnosis.suggested_fix}</p><h4>How to verify</h4><p>{run.diagnosis.verification_steps}</p><div className="verification"><Clock3 size={14}/> Fix not yet verified for this run</div>
        </>:<div className="notice">{run.analysis_status==='failed'?`Analysis could not finish (${run.analysis_error_code||'unknown error'}).`:'Analysis is pending. Refresh shortly to check again.'}</div>}
      </section>
      {run.sanitized_log_excerpt&&<details className="log-excerpt"><summary><Code2 size={15}/> Sanitized log excerpt <ChevronDown size={14}/></summary><pre>{run.sanitized_log_excerpt}</pre><small>Excerpt is size-limited. Secret redaction is best-effort.</small></details>}
      {link&&<a className="workflow-link" href={link} target="_blank" rel="noreferrer">Open run in GitHub <ArrowUpRight size={15}/></a>}
    </>}
  </aside>;
}

export function Dashboard({config, session, signOut}) {
  const [runs,setRuns] = useState([]); const [repository,setRepository] = useState(''); const [cursor,setCursor]=useState(null); const [loading,setLoading]=useState(true); const [error,setError]=useState(''); const [updated,setUpdated]=useState(null); const [filter,setFilter]=useState('all'); const [search,setSearch]=useState(''); const [selected,setSelected]=useState(null); const [detail,setDetail]=useState(null); const [detailBusy,setDetailBusy]=useState(false); const [detailError,setDetailError]=useState('');
  const detailController=useRef(null); const listController=useRef(null);
  async function load(more=false) {
    listController.current?.abort(); const controller=new AbortController(); listController.current=controller;
    setLoading(true); setError('');
    try {
      const result=await request(config, session.token, '/runs?limit=25'+(more&&cursor?'&cursor='+encodeURIComponent(cursor):''),controller.signal);
      setRuns(previous=>more?[...new Map([...previous,...result.runs].map(run=>[run.run_key,run])).values()]:result.runs); setRepository(result.repository); setCursor(result.next_cursor); setUpdated(new Date());
    } catch(e) {if(e.name==='AbortError')return; if(e.status===401)signOut(e.message); else setError(e.message);}
    finally {if(!controller.signal.aborted)setLoading(false);}
  }
  async function choose(run) {
    detailController.current?.abort(); const controller=new AbortController(); detailController.current=controller;
    setSelected(run.run_key);setDetail(null);setDetailBusy(true);setDetailError('');
    try {const result=await request(config,session.token,`/runs/${run.run_id}/attempts/${run.run_attempt}`,controller.signal);setDetail(result.run);}
    catch(e) {if(e.name==='AbortError')return;if(e.status===401)signOut(e.message);else setDetailError(e.message);}
    finally {if(!controller.signal.aborted)setDetailBusy(false);}
  }
  function refresh() {load(); if(detail)choose(detail);}
  useEffect(()=>{load();return()=>{listController.current?.abort();detailController.current?.abort();};},[]);
  const stats=runStats(runs);
  const visible=runs.filter(run=>(filter==='all'||filter==='failed'&&isFailed(run)||filter==='passed'&&run.conclusion==='success')&&`${run.name} ${run.head_branch} ${run.head_sha} ${run.run_id}`.toLowerCase().includes(search.toLowerCase()));
  return <div className="app-shell"><aside className="sidebar"><Brand light/><span className="workspace-label">TEAM WORKSPACE</span><div className="workspace"><span className="workspace-avatar">D</span><div><strong>DeployIQ project</strong><small>Pipeline monitoring</small></div><ChevronDown size={14}/></div><nav><span className="nav-active"><LayoutDashboard size={18}/> Overview <span className="nav-dot"/></span><a href="https://github.com/Bhanuch2006/deployiq/actions" target="_blank" rel="noreferrer"><Github size={18}/> GitHub Actions <ArrowUpRight size={14}/></a></nav><div className="sidebar-bottom"><div className="architecture-note"><ShieldCheck size={18}/><strong>Evidence before advice.</strong><p>Every diagnosis shows its source. Every fix still needs verification.</p></div><div className="user-row"><span className="user-avatar">{session.username.slice(0,1).toUpperCase()}</span><div><strong>{session.username}</strong><small>Team member</small></div><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={()=>signOut()}><LogOut size={17}/></button></div></div></aside>
    <main className="dashboard-main"><header className="topbar"><span className="breadcrumb">Workspace <ChevronRight size={13}/> <strong>Overview</strong></span><span className="region"><span/> US East · N. Virginia</span></header><div className="page-content"><div className="page-heading"><div><span className="eyebrow muted">YOUR DELIVERY, IN FOCUS</span><h1>Pipeline overview<span>.</span></h1><p>Follow each release. Understand every failure.</p></div><button className="secondary refresh-button" disabled={loading} onClick={refresh}><RefreshCw size={15} className={loading?'spin':''}/> Refresh</button></div>
      <div className="repository-line"><span className="repo-chip"><Github size={15}/>{repository||'Loading repository…'}</span><span className="sync-status"><span className={updated?'status-dot':'status-dot waiting'}/>{updated?`Synced ${updated.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`:'Connecting…'}</span></div>
      {error&&<div className="error" role="alert">{error}</div>}
      <div className="metrics">{[[Activity,'Runs recorded',loading&&!runs.length?'—':stats.total,'Loaded history',''],[CheckCircle2,'Success rate',stats.successRate===null?'—':stats.successRate+'%','Passed ÷ passed + failed','green'],[XCircle,'Failed runs',loading&&!runs.length?'—':stats.failed,'Includes timed-out runs','red'],[Sparkles,'Diagnoses ready',loading&&!runs.length?'—':stats.diagnosed,'AI and rules, clearly labeled','gold']].map(([Icon,label,value,note,tone])=><section className={`metric ${tone}`} key={label}><div><span>{label}</span><Icon size={18}/></div><strong>{value}</strong><small>{note}</small></section>)}</div><p className="metric-caption">Metrics reflect the {runs.length} loaded runs, not all historical runs. Cancelled and skipped runs are excluded from success rate.</p>
      <div className={`workbench ${selected?'has-selection':''}`}><section className="runs-panel"><div className="runs-heading"><div><h2>Workflow runs <span>{runs.length}</span></h2><p>Real events from your connected repository.</p></div><GitBranch size={20}/></div><div className="table-controls"><div className="tabs" role="group" aria-label="Filter workflow runs">{[['all','All runs'],['failed','Failed'],['passed','Passed']].map(([key,label])=><button key={key} className={filter===key?'active':''} aria-pressed={filter===key} onClick={()=>setFilter(key)}>{label}</button>)}</div><label className="search"><Search size={15}/><input aria-label="Search runs" placeholder="Search runs…" value={search} onChange={e=>setSearch(e.target.value)}/></label></div>
        <div className="run-list"><div className="run-columns"><span>WORKFLOW / COMMIT</span><span>RESULT</span><span>RECORDED</span></div>{loading&&!runs.length?<div className="list-empty"><Loader2 size={22} className="spin"/><h3>Loading your pipeline history</h3></div>:visible.length?visible.map(run=><button key={run.run_key} className={`run-row ${selected===run.run_key?'selected':''}`} onClick={()=>choose(run)} aria-label={`Open ${run.name || 'workflow'} run ${run.run_id}`}><span className="run-description"><span className={`run-symbol ${run.conclusion==='success'?'passed':isFailed(run)?'failed':''}`}>{run.conclusion==='success'?<Check size={16}/>:isFailed(run)?<X size={16}/>:<Circle size={13}/>}</span><span><strong>{run.name||'Workflow run'}</strong><small><GitBranch size={11}/>{run.head_branch||'—'}<i>·</i><code>{run.head_sha?.slice(0,7)||'—'}</code><i>·</i>#{run.run_id}</small></span></span><span className="run-result"><Badge run={run}/>{run.analysis_source&&<small>{diagnosisLabel(run)}</small>}</span><span className="run-time">{when(run.received_at)}<ChevronRight size={15}/></span></button>):<div className="list-empty"><GitBranch size={28}/><h3>{runs.length?'No matching runs':'Your next run starts the story'}</h3><p>{runs.length?'Try another filter or search.':'Complete a GitHub workflow, then refresh to see it here.'}</p></div>}</div>{cursor&&<div className="load-more"><button className="secondary" disabled={loading} onClick={()=>load(true)}>{loading?<Loader2 className="spin" size={14}/>:<ArrowDown size={14}/>} Load older runs</button></div>}
      </section><Detail run={detail} busy={detailBusy} error={detailError} onClose={()=>{detailController.current?.abort();setSelected(null);setDetail(null);setDetailError('');setDetailBusy(false);}}/></div><footer className="dashboard-footer"><span><LockKeyhole size={12}/> Private team data · Read-only dashboard</span><span>DeployIQ / Built for better releases</span></footer></div></main>
  </div>;
}

export default function App() {
  const [config,setConfig]=useState(initialConfig);const [session,setSession]=useState(null);const [notice,setNotice]=useState('');
  function signOut(message='') {setSession(null);setNotice(message);}
  useEffect(()=>{if(!session)return;const timer=setTimeout(()=>signOut('Your session has expired. Sign in again.'),Math.max(0,session.expiresAt-Date.now()));return()=>clearTimeout(timer);},[session]);
  return session?<Dashboard config={config} session={session} signOut={signOut}/>:<SignIn config={config} setConfig={setConfig} onSession={value=>{setNotice('');setSession(value);}} notice={notice}/>;
}

