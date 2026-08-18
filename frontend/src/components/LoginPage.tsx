import { FormEvent, useState } from 'react'
import { Globe2, KeyRound, LoaderCircle, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react'
import { login, type SessionUser } from '../auth'

export default function LoginPage({ mode, onLogin }: { mode: 'internet' | 'intranet'; onLogin: (user: SessionUser) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try { onLogin(await login(username, password, otp)) }
    catch (reason) {
      const message = reason instanceof Error ? reason.message : '登录失败'
      setError(message)
    }
    finally { setBusy(false) }
  }
  return <main className="login-screen">
    <section className="login-intro"><div className="login-brand"><span><Globe2 size={34}/><i/></span><div><b>国境卫士</b><small>GLOBAL HEALTH SENTINEL</small></div></div><div><span className="eyebrow"><i className="pulse-dot"/>SECURE PUBLIC HEALTH PLATFORM</span><h1>{mode === 'internet' ? '全球公共卫生互联网监测平台' : '口岸公共卫生内网预警平台'}</h1><p>{mode === 'internet' ? '汇聚全球权威疫情数据，开展风险评分并向内网单向安全摆渡。' : '离线接收全球疫情态势，完成旅客风险匹配、口岸预警与布控研判。'}</p><div className="login-security"><span><ShieldCheck size={18}/>平台隔离</span><span><LockKeyhole size={18}/>加密传输</span><span><UserRound size={18}/>角色授权</span></div></div></section>
    <form className="login-card" onSubmit={submit}><header><span className="panel__eyebrow">IDENTITY ACCESS</span><h2>身份认证</h2><p>请输入本平台授权账号</p></header><label><span>用户名</span><div><UserRound size={17}/><input autoComplete="username" required value={username} onChange={event=>setUsername(event.target.value)} placeholder="请输入用户名"/></div></label><label><span>密码</span><div><LockKeyhole size={17}/><input type="password" autoComplete="current-password" required value={password} onChange={event=>setPassword(event.target.value)} placeholder="请输入密码"/></div></label><label><span>动态验证码（已启用 MFA 的账号必填）</span><div><KeyRound size={17}/><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={otp} onChange={event=>setOtp(event.target.value.replace(/\D/g,'').slice(0,6))} placeholder="6 位动态验证码"/></div></label>{error&&<div className="login-error">{error}</div>}<button className="primary-button full-width" disabled={busy}>{busy?<><LoaderCircle className="spin" size={17}/>正在验证</>:<><ShieldCheck size={17}/>安全登录</>}</button><footer>连续 5 次失败将锁定账号 15 分钟</footer></form>
  </main>
}
