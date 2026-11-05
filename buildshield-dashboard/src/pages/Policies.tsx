import { useState } from 'react';
import { CircleCheck, CircleX, TriangleAlert } from 'lucide-react';
import { getPolicies } from '../api';
import { useFetch } from '../useFetch';
import type { PolicyData, PolicyMode } from '../types';
import { Loading, ErrorState } from '../components/PageState';

const modes: { key: PolicyMode; label: string }[] = [
  { key: 'report', label: 'Report Only' },
  { key: 'warn', label: 'Warn on PR' },
  { key: 'enforce', label: 'Enforce Blocking Check Runs' },
];

function Switch({
  checked,
  locked,
  label,
  onChange,
}: {
  checked: boolean;
  locked: boolean;
  label: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={locked}
      className="switch"
      onClick={() => onChange(!checked)}
    >
      <span className="switch-knob" />
    </button>
  );
}

function CheckPreview({ mode, blockRuleOn }: { mode: PolicyMode; blockRuleOn: boolean }) {
  let tone: 'bad' | 'warn' | 'neutral';
  let label: string;
  let message: string;

  if (mode === 'enforce' && blockRuleOn) {
    tone = 'bad';
    label = 'Failed:';
    message = 'Policies enforced. New Critical Vulnerability found.';
  } else if (mode === 'enforce') {
    tone = 'warn';
    label = 'Warning:';
    message = 'Rule 1 is off, so the new Critical Vulnerability does not block this pull request.';
  } else if (mode === 'warn') {
    tone = 'warn';
    label = 'Warning:';
    message = 'New Critical Vulnerability found. Review it before merging.';
  } else {
    tone = 'neutral';
    label = 'Reported:';
    message = 'New Critical Vulnerability found. The pull request is not blocked.';
  }

  const detail = tone === 'bad' ? '1 critical block' : '1 critical finding';

  return (
    <div className={`check check-${tone}`}>
      {tone === 'bad' && <CircleX size={22} aria-hidden="true" />}
      {tone === 'warn' && <TriangleAlert size={22} aria-hidden="true" />}
      {tone === 'neutral' && <CircleCheck size={22} aria-hidden="true" />}
      <div>
        <p className="check-title">BuildShield PR Security Check</p>
        <p>
          <strong className="check-status">{label}</strong> {message}
        </p>
        <p className="muted">Checked 14 files | {detail}</p>
      </div>
    </div>
  );
}

function PoliciesView({ initial }: { initial: PolicyData }) {
  const [mode, setMode] = useState<PolicyMode>(initial.mode);
  const [rules, setRules] = useState(initial.rules);

  const activeCount = rules.filter((r) => r.enabled).length;
  const blockRuleOn = rules.find((r) => r.id === 'block-new')?.enabled ?? false;

  const setRule = (id: string, enabled: boolean) => {
    setRules((current) => current.map((r) => (r.id === id ? { ...r, enabled } : r)));
  };

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="mode-title">
        <h2 id="mode-title" className="section-title">
          Deterministic Policy Mode
        </h2>
        <p className="muted">Determines build failure behavior when scan violations are detected.</p>
        <div className="segmented" role="group" aria-label="Policy mode">
          {modes.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={mode === key}
              onClick={() => setMode(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="panel" aria-labelledby="rules-title">
        <div className="panel-head">
          <h2 id="rules-title" className="section-title">
            Transparent Risk &amp; Policy Rules
          </h2>
          <span className="chip">
            {activeCount} active {activeCount === 1 ? 'policy' : 'policies'}
          </span>
        </div>
        <ul className="rules">
          {rules.map((rule) => (
            <li key={rule.id} className="rule-row">
              <span>{rule.text}</span>
              <span className="rule-control">
                {rule.locked && <span className="muted">Always on</span>}
                <Switch
                  checked={rule.enabled}
                  locked={rule.locked}
                  label={rule.text}
                  onChange={(value) => setRule(rule.id, value)}
                />
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" aria-labelledby="preview-title">
        <h2 id="preview-title" className="section-title">
          GitHub Check Run Output Preview
        </h2>
        <CheckPreview mode={mode} blockRuleOn={blockRuleOn} />
      </section>
    </div>
  );
}

export default function Policies() {
  const { state, retry } = useFetch(getPolicies);

  if (state.status === 'loading') return <Loading label="Loading policies" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  return <PoliciesView initial={state.data} />;
}