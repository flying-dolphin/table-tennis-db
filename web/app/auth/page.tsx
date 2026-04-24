"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { X, Mail, Lock, User, Eye, EyeOff, Loader2, CheckCircle2, Circle, ShieldCheck } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { APP_NAME } from "@/lib/constants";
import Image from "next/image";

type Tab = "login" | "register";
type FormState = "idle" | "loading" | "error";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const CODE_COOLDOWN = 60;

export default function AuthPage() {
  const [tab, setTab] = useState<Tab>("login");
  const [formState, setFormState] = useState<FormState>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const router = useRouter();

  // Login
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Register
  const [regEmail, setRegEmail] = useState("");
  const [regUsername, setRegUsername] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirm, setRegConfirm] = useState("");
  const [regCode, setRegCode] = useState("");

  // Email code state
  const [codeSending, setCodeSending] = useState(false);
  const [codeCooldown, setCodeCooldown] = useState(0);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Password match derived state
  const passwordMismatch = regConfirm.length > 0 && regPassword !== regConfirm;
  const passwordMatch = regConfirm.length > 0 && regPassword === regConfirm;

  useEffect(() => {
    fetch("/api/v1/auth/me", { credentials: "include", cache: "no-store" })
      .then((res) => { if (res.ok) router.replace("/me"); })
      .catch(() => { });
  }, [router]);

  useEffect(() => {
    return () => { if (cooldownRef.current) clearInterval(cooldownRef.current); };
  }, []);

  function switchTab(t: Tab) {
    setTab(t);
    setErrorMsg("");
    setFormState("idle");
  }

  async function handleSendCode() {
    if (codeSending || codeCooldown > 0) return;
    if (!EMAIL_RE.test(regEmail.trim())) {
      setErrorMsg("请先输入有效的邮箱地址");
      return;
    }
    setErrorMsg("");
    setCodeSending(true);
    try {
      const res = await fetch("/api/v1/auth/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: regEmail.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.message || "发送失败，请重试");
        return;
      }
      setCodeCooldown(CODE_COOLDOWN);
      cooldownRef.current = setInterval(() => {
        setCodeCooldown((v) => {
          if (v <= 1) { clearInterval(cooldownRef.current!); return 0; }
          return v - 1;
        });
      }, 1000);
    } catch {
      setErrorMsg("网络错误，请重试");
    } finally {
      setCodeSending(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!agreed) { setErrorMsg("请先阅读并同意用户协议"); return; }
    if (formState === "loading") return;
    setErrorMsg("");
    setFormState("loading");
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.message || "登录失败，请重试");
        setFormState("error");
        return;
      }
      router.push("/");
      router.refresh();
    } catch {
      setErrorMsg("网络错误，请重试");
      setFormState("error");
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!agreed) { setErrorMsg("请先阅读并同意用户协议"); return; }
    if (formState === "loading") return;
    setErrorMsg("");
    if (regPassword !== regConfirm) {
      setErrorMsg("两次输入的密码不一致");
      setFormState("error");
      return;
    }
    if (!regCode.trim()) {
      setErrorMsg("请输入邮箱验证码");
      setFormState("error");
      return;
    }
    setFormState("loading");
    try {
      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: regEmail, username: regUsername, password: regPassword, code: regCode }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.message || "注册失败，请重试");
        setFormState("error");
        return;
      }
      router.push("/");
      router.refresh();
    } catch {
      setErrorMsg("网络错误，请重试");
      setFormState("error");
    }
  }

  const inputWrapperCls = "relative flex items-center border-b border-gray-100 py-4 focus-within:border-brand-primary transition-all";
  const inputIconCls = "text-text-primary mr-3 opacity-70 shrink-0";
  const inputBaseCls = "flex-1 bg-transparent outline-none text-[16px] text-text-primary placeholder:text-text-tertiary min-w-0";

  return (
    <main className="min-h-screen bg-white relative flex flex-col overflow-x-hidden font-body">
      <div className="absolute top-0 left-0 w-full h-[40vh] pointer-events-none overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,_#EBF4FF_0%,_#FFFFFF_70%)] opacity-80" />
        <div className="absolute top-[-10%] left-[-5%] w-[40%] h-[40%] bg-blue-50/50 blur-[80px] rounded-full rotate-12" />
        <div className="absolute top-[10%] right-[-10%] w-[50%] h-[50%] bg-brand-soft/20 blur-[100px] rounded-full" />
      </div>

      <div className="w-full flex justify-start p-6 relative z-20">
        <Link href="/" className="text-text-primary p-2 hover:bg-white/50 backdrop-blur-sm rounded-full transition-colors border border-white/20">
          <X size={24} strokeWidth={1.5} />
        </Link>
      </div>

      <div className="w-full max-w-[400px] mx-auto px-8 flex-1 flex flex-col relative z-10">
        <div className="flex flex-col items-center mt-2 mb-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="relative mb-6"
          >
            <div className="absolute inset-0 bg-brand-primary/20 blur-3xl rounded-full scale-150" />
            <div className="relative z-10 p-1 bg-white/40 backdrop-blur-md rounded-[28px] border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.04)] w-24 h-24">
              <Image src="/images/logo.png" alt="Logo" className="object-contain drop-shadow-sm w-full h-full" fill />
            </div>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="text-center">
            <h1 className="text-[28px] font-bold text-text-primary tracking-tight">
              {tab === "login" ? "豆包球谱" : `加入${APP_NAME}`}
            </h1>
            <p className="mt-2 text-body text-text-secondary opacity-70">
              {tab === "login" ? "登录以继续探索精彩内容" : "开启您的乒乓数据洞察之旅"}
            </p>
          </motion.div>
        </div>

        <div className="flex-1">
          <AnimatePresence mode="wait">
            {tab === "login" ? (
              <motion.form
                key="login"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.4 }}
                onSubmit={handleLogin}
                className="space-y-4"
              >
                <div className="space-y-1">
                  <label className="text-caption font-semibold text-text-tertiary ml-1 uppercase tracking-wider">邮箱</label>
                  <div className={inputWrapperCls}>
                    <Mail size={18} strokeWidth={2} className={inputIconCls} />
                    <input
                      type="email" required
                      value={loginEmail}
                      onChange={(e) => setLoginEmail(e.target.value)}
                      placeholder="请输入邮箱地址"
                      className={inputBaseCls}
                    />
                  </div>
                </div>

                <div className="space-y-1 pt-2">
                  <div className="flex justify-between items-center ml-1">
                    <label className="text-caption font-semibold text-text-tertiary uppercase tracking-wider">密码</label>
                    <button type="button" className="text-caption text-brand-deep font-medium hover:underline">忘记密码?</button>
                  </div>
                  <div className={inputWrapperCls}>
                    <Lock size={18} strokeWidth={2} className={inputIconCls} />
                    <input
                      type={showPassword ? "text" : "password"} required
                      value={loginPassword}
                      onChange={(e) => setLoginPassword(e.target.value)}
                      placeholder="请输入登录密码"
                      className={inputBaseCls}
                    />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="text-text-tertiary ml-2 opacity-50 hover:opacity-100 transition-opacity shrink-0">
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>

                {errorMsg && (
                  <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-caption text-state-danger-text bg-state-danger/5 p-3 rounded-lg border border-state-danger/10">
                    {errorMsg}
                  </motion.p>
                )}

                <div className="pt-8 space-y-6">
                  <button
                    type="submit"
                    disabled={formState === "loading"}
                    className="w-full py-4 bg-brand-deep text-white rounded-2xl font-bold text-[17px] shadow-[0_12px_24px_rgba(107,151,203,0.3)] hover:bg-brand-strong hover:-translate-y-0.5 transition-all active:scale-[0.98] disabled:opacity-70 flex justify-center items-center"
                  >
                    {formState === "loading" ? <Loader2 className="animate-spin" size={20} /> : "登 录"}
                  </button>
                  <div className="text-center text-text-secondary text-[14px]">
                    还没有账号? <button type="button" onClick={() => switchTab("register")} className="text-brand-deep font-bold hover:underline">立即注册</button>
                  </div>
                </div>
              </motion.form>
            ) : (
              <motion.form
                key="register"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.4 }}
                onSubmit={handleRegister}
                className="space-y-2"
              >
                {/* Email + send code button */}
                <div className={inputWrapperCls}>
                  <Mail size={18} strokeWidth={2} className={inputIconCls} />
                  <input
                    type="email" required
                    value={regEmail}
                    onChange={(e) => { setRegEmail(e.target.value); setErrorMsg(""); }}
                    placeholder="请输入邮箱"
                    className={inputBaseCls}
                  />
                  <button
                    type="button"
                    onClick={handleSendCode}
                    disabled={codeSending || codeCooldown > 0}
                    className="ml-2 shrink-0 text-[13px] font-semibold text-brand-deep disabled:text-gray-400 whitespace-nowrap flex items-center gap-1"
                  >
                    {codeSending
                      ? <Loader2 size={13} className="animate-spin" />
                      : codeCooldown > 0
                        ? `${codeCooldown}s`
                        : "获取验证码"}
                  </button>
                </div>

                {/* Verification code */}
                <div className={inputWrapperCls}>
                  <ShieldCheck size={18} strokeWidth={2} className={inputIconCls} />
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={regCode}
                    onChange={(e) => { setRegCode(e.target.value.replace(/\D/g, "")); setErrorMsg(""); }}
                    placeholder="6 位邮箱验证码"
                    className={inputBaseCls}
                  />
                </div>

                {/* Username */}
                <div className={inputWrapperCls}>
                  <User size={18} strokeWidth={2} className={inputIconCls} />
                  <input
                    type="text" required
                    value={regUsername}
                    onChange={(e) => setRegUsername(e.target.value)}
                    placeholder="请输入用户名（3-20位字母数字）"
                    className={inputBaseCls}
                  />
                </div>

                {/* Password */}
                <div className={inputWrapperCls}>
                  <Lock size={18} strokeWidth={2} className={inputIconCls} />
                  <input
                    type={showPassword ? "text" : "password"} required
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="请设置密码（至少 8 位）"
                    className={inputBaseCls}
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="text-text-tertiary ml-2 opacity-50 hover:opacity-100 transition-opacity shrink-0">
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                {/* Confirm password with real-time match feedback */}
                <div className={`${inputWrapperCls} ${passwordMismatch ? "!border-red-400" : passwordMatch ? "!border-green-400" : ""}`}>
                  <Lock
                    size={18} strokeWidth={2}
                    className={`mr-3 shrink-0 transition-colors ${passwordMismatch ? "text-red-400 opacity-100" : passwordMatch ? "text-green-500 opacity-100" : "text-text-primary opacity-70"}`}
                  />
                  <input
                    type={showPassword ? "text" : "password"} required
                    value={regConfirm}
                    onChange={(e) => { setRegConfirm(e.target.value); setErrorMsg(""); }}
                    placeholder="请再次确认密码"
                    className={`${inputBaseCls} ${passwordMismatch ? "text-red-500" : ""}`}
                  />
                  {passwordMatch && <CheckCircle2 size={16} className="text-green-500 ml-2 shrink-0" />}
                </div>
                {passwordMismatch && (
                  <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="text-[12px] text-red-500 pl-7">
                    两次输入的密码不一致
                  </motion.p>
                )}

                {errorMsg && (
                  <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-caption text-state-danger-text p-3 bg-state-danger/5 rounded-lg border border-state-danger/10">
                    {errorMsg}
                  </motion.p>
                )}

                <div className="pt-6 space-y-6">
                  <button
                    type="submit"
                    disabled={formState === "loading" || passwordMismatch}
                    className="w-full py-4 bg-brand-deep text-white rounded-2xl font-bold text-[17px] shadow-[0_12px_24px_rgba(107,151,203,0.3)] hover:bg-brand-strong hover:-translate-y-0.5 transition-all active:scale-[0.98] disabled:opacity-70 flex justify-center items-center"
                  >
                    {formState === "loading" ? <Loader2 className="animate-spin" size={20} /> : "注 册"}
                  </button>
                  <div className="text-center text-text-secondary text-[14px]">
                    已有账号? <button type="button" onClick={() => switchTab("login")} className="text-brand-deep font-bold hover:underline">去登录</button>
                  </div>
                </div>
              </motion.form>
            )}
          </AnimatePresence>
        </div>

        <div className="mt-auto py-8">
          <button type="button" onClick={() => setAgreed(!agreed)} className="flex items-start gap-2 group text-left">
            <div className={`mt-0.5 transition-colors ${agreed ? "text-brand-primary" : "text-gray-300 group-hover:text-gray-400"}`}>
              {agreed ? <CheckCircle2 size={16} fill="currentColor" className="text-white bg-brand-primary rounded-full shadow-sm" /> : <Circle size={16} />}
            </div>
            <p className="text-[12px] text-text-tertiary leading-relaxed">
              阅读并同意<Link href="/terms" className="text-brand-deep font-medium hover:underline mx-0.5">《用户协议》</Link>和<Link href="/privacy" className="text-brand-deep font-medium hover:underline mx-0.5">《隐私政策》</Link>，登录后解锁自然语言搜索功能
            </p>
          </button>
        </div>
      </div>
    </main>
  );
}
