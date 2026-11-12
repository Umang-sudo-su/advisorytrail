import { useState } from 'react';
import {
  ArrowRight,
  CircleCheck,
  Eye,
  EyeOff,
  GitPullRequest,
  KeyRound,
  LoaderCircle,
  Lock,
  Mail,
  TriangleAlert,
  User,
} from 'lucide-react';
import { useAuth } from '../AuthContext';
import { loginUser, registerUser, verifyTwoFactor } from '../api';
import './Login.css';

type Mode = 'login' | 'register';

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong. Please try again.';

export default function Login() {
  const { login } = useAuth();

  const [mode, setMode] = useState<Mode>('login');
  const [identifier, setIdentifier] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState('');

  const isRegistering = mode === 'register';

  const switchMode = () => {
    setMode(isRegistering ? 'login' : 'register');
    setError('');
    setNotice('');
    setPassword('');
    setShowPassword(false);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    const trimmedIdentifier = identifier.trim();

    setError('');
    setNotice('');

    if (!trimmedIdentifier || !password) {
      setError('Enter your credentials to continue.');
      return;
    }

    setSubmitting(true);

    try {
      if (isRegistering) {
        if (!email.trim()) {
          setError('Enter an email address for your account.');
          return;
        }
        if (password.length < 8) {
          setError('Password must be at least 8 characters long.');
          return;
        }

        await registerUser({ username: trimmedIdentifier, email: email.trim(), password });
        setMode('login');
        setPassword('');
        setNotice('Account created. Sign in with your new credentials.');
        return;
      }

      const result = await loginUser(trimmedIdentifier, password);
      if (result.kind === '2fa') {
        setChallenge(result.challengeToken);
        setPassword('');
        setNotice('Enter the 6-digit code from your authenticator app, or a recovery code.');
        return;
      }

      // Successful login replaces this screen with the dashboard.
      login(result.token, remember);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerify = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!challenge || submitting) return;

    setError('');
    setSubmitting(true);
    try {
      const token = await verifyTwoFactor(challenge, code.trim());
      login(token, remember);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const restartSignIn = () => {
    setChallenge(null);
    setCode('');
    setError('');
    setNotice('');
  };

  return (
    <div className="login-page">
      <div className="login-shell">
        <aside className="login-brand">
          <img src="/assets/logo-mark-light.png" alt="" className="brand-shield" aria-hidden="true" />

          <div className="brand-top">
            <img src="/assets/logo-lockup-light.png" alt="BuildShield" className="login-lockup" />
            <p className="brand-tagline">Scan &bull; Detect &bull; Protect</p>
          </div>

          <div className="brand-copy">
            <h3>Every pull request, checked before it merges.</h3>
            <p>
              BuildShield runs dependency scanners on your repositories and turns raw results into
              evidence-backed findings, policies and audit trails.
            </p>
            <ul className="brand-points">
              <li>
                <CircleCheck size={16} aria-hidden="true" />
                OSV-Scanner findings normalized and de-duplicated
              </li>
              <li>
                <GitPullRequest size={16} aria-hidden="true" />
                Baseline diffing separates new risk from existing noise
              </li>
              <li>
                <Lock size={16} aria-hidden="true" />
                Deterministic policy gates for GitHub Check Runs
              </li>
            </ul>
          </div>
        </aside>

        <section className="login-form-panel">
          <span className="form-eyebrow">
            <Lock size={13} aria-hidden="true" />
            {isRegistering ? 'New account' : 'Secure sign in'}
          </span>

          <h1>{challenge ? 'Two-factor verification' : isRegistering ? 'Create your account' : 'Welcome back'}</h1>
          <p className="form-subtitle">
            {isRegistering
              ? 'Register to start scanning your repositories.'
              : 'Sign in to review scans, findings and policy decisions.'}
          </p>

          {challenge ? (
            <form className="login-form" onSubmit={handleVerify} noValidate>
              <div className="field">
                <label className="field-label" htmlFor="auth-code">
                  Authenticator or recovery code
                </label>
                <div className="field-control">
                  <KeyRound size={18} aria-hidden="true" />
                  <input
                    id="auth-code"
                    name="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="6-digit code or recovery code"
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    required
                    autoFocus
                  />
                </div>
              </div>

              {error && (
                <p className="alert alert-error" role="alert">
                  <TriangleAlert size={16} aria-hidden="true" />
                  {error}
                </p>
              )}

              {notice && (
                <p className="alert alert-success" role="status">
                  <CircleCheck size={16} aria-hidden="true" />
                  {notice}
                </p>
              )}

              <button type="submit" className="submit-button" disabled={submitting || code.trim().length < 6}>
                {submitting ? (
                  <>
                    <LoaderCircle size={18} className="spin" aria-hidden="true" />
                    Verifying…
                  </>
                ) : (
                  <>
                    Verify and sign in
                    <ArrowRight size={18} aria-hidden="true" />
                  </>
                )}
              </button>

              <button type="button" className="link-button" onClick={restartSignIn}>
                Start over
              </button>
            </form>
          ) : (
          <form className="login-form" onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label className="field-label" htmlFor="auth-identifier">
                {isRegistering ? 'Username' : 'Username or email'}
              </label>
              <div className="field-control">
                <User size={18} aria-hidden="true" />
                <input
                  id="auth-identifier"
                  name="identifier"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="username"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  required
                  autoFocus
                />
              </div>
            </div>

            {isRegistering && (
              <div className="field">
                <label className="field-label" htmlFor="auth-email">
                  Email
                </label>
                <div className="field-control">
                  <Mail size={18} aria-hidden="true" />
                  <input
                    id="auth-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    autoCapitalize="none"
                    spellCheck={false}
                    placeholder="Email address"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
              </div>
            )}

            <div className="field">
              <label className="field-label" htmlFor="auth-password">
                Password
              </label>
              <div className="field-control">
                <Lock size={18} aria-hidden="true" />
                <input
                  id="auth-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={isRegistering ? 'new-password' : 'current-password'}
                  placeholder={isRegistering ? 'At least 8 characters' : 'Your password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                </button>
              </div>
            </div>

            {!isRegistering && (
              <div className="form-row">
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(event) => setRemember(event.target.checked)}
                  />
                  <span>Keep me signed in on this device</span>
                </label>
              </div>
            )}

            {error && (
              <p className="alert alert-error" role="alert">
                <TriangleAlert size={16} aria-hidden="true" />
                {error}
              </p>
            )}

            {notice && (
              <p className="alert alert-success" role="status">
                <CircleCheck size={16} aria-hidden="true" />
                {notice}
              </p>
            )}

            <button type="submit" className="submit-button" disabled={submitting}>
              {submitting ? (
                <>
                  <LoaderCircle size={18} className="spin" aria-hidden="true" />
                  {isRegistering ? 'Creating account…' : 'Signing in…'}
                </>
              ) : (
                <>
                  {isRegistering ? 'Create account' : 'Sign in'}
                  <ArrowRight size={18} aria-hidden="true" />
                </>
              )}
            </button>
          </form>
          )}

          {!challenge && (
            <p className="form-footer">
              {isRegistering ? 'Already have an account?' : 'New to BuildShield?'}
              <button type="button" className="link-button" onClick={switchMode}>
                {isRegistering ? 'Sign in' : 'Create an account'}
              </button>
            </p>
          )}

          <p className="session-note">
            <Lock size={12} aria-hidden="true" />
            You stay signed in for this session. Closing the tab or signing out ends it.
          </p>
        </section>
      </div>
    </div>
  );
}
