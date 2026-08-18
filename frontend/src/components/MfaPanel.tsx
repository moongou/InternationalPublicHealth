import { FormEvent, useEffect, useState } from 'react'
import { CheckCircle2, Copy, KeyRound, LoaderCircle, RefreshCw, ShieldCheck } from 'lucide-react'
import { postJson, requestJson } from '../api'
import { clearSession } from '../auth'

interface MfaState {
  mfa_enabled: boolean
  mfa_verified: boolean
}

interface MfaSetup {
  secret: string
  provisioning_uri: string
}

export default function MfaPanel() {
  const [state, setState] = useState<MfaState | null>(null)
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    requestJson<MfaState>('/auth/me').then(setState).catch(error => {
      setMessage(error instanceof Error ? error.message : '安全状态加载失败')
    })
  }, [])

  const begin = async () => {
    setBusy(true); setMessage('')
    try { setSetup(await postJson<MfaSetup>('/auth/mfa/setup')) }
    catch (error) { setMessage(error instanceof Error ? error.message : '初始化失败') }
    finally { setBusy(false) }
  }

  const enable = async (event: FormEvent) => {
    event.preventDefault()
    if (!/^\d{6}$/.test(code)) return
    setBusy(true); setMessage('')
    try {
      await postJson('/auth/mfa/enable', { code })
      clearSession()
      window.location.reload()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '动态验证码校验失败')
      setBusy(false)
    }
  }

  const copySecret = async () => {
    if (!setup) return
    await navigator.clipboard.writeText(setup.secret)
    setMessage('密钥已复制，请妥善保管且不要通过网络传输')
  }

  return <section className="panel mfa-panel">
    <header className="panel__header"><div><span className="panel__eyebrow">MULTI-FACTOR AUTHENTICATION</span><h2>双因素认证</h2></div><ShieldCheck size={21} className="text-teal"/></header>
    <div className="backup-policy"><span><KeyRound size={19}/></span><div><b>管理员敏感操作要求 TOTP 动态验证码</b><p>密钥仅在本次绑定时显示。绑定完成后需要重新登录，使访问令牌获得 MFA 验证标记。</p></div></div>
    {state?.mfa_enabled && !setup && <div className="mfa-status result-ok"><CheckCircle2 size={16}/>双因素认证已启用{state.mfa_verified ? '，当前会话已验证' : '，请退出后使用动态验证码重新登录'}</div>}
    {!setup && !state?.mfa_enabled && <button className="primary-button" disabled={busy} onClick={begin}>{busy?<LoaderCircle className="spin" size={16}/>:<RefreshCw size={16}/>} 开始绑定认证器</button>}
    {setup && <form className="mfa-enrollment" onSubmit={enable}>
      <ol><li>在离线认证器中选择“输入设置密钥”。</li><li>录入下方密钥，类型选择“基于时间”。</li><li>输入认证器生成的 6 位验证码完成绑定。</li></ol>
      <div className="mfa-secret"><code>{setup.secret}</code><button type="button" className="icon-button" title="复制密钥" onClick={copySecret}><Copy size={15}/></button></div>
      <details><summary>显示标准配置 URI</summary><code>{setup.provisioning_uri}</code></details>
      <label><span>6 位动态验证码</span><input required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event=>setCode(event.target.value.replace(/\D/g,'').slice(0,6))} placeholder="000000"/></label>
      <button className="primary-button" disabled={busy || code.length !== 6}>{busy?<LoaderCircle className="spin" size={16}/>:<ShieldCheck size={16}/>}验证并启用</button>
    </form>}
    {message && <div className="login-error mfa-message">{message}</div>}
  </section>
}
