"use client";

import React, { useState } from "react";
import { Cpu, Github, Lock, Mail, ArrowRight, Check, AlertCircle } from "lucide-react";

interface AuthViewProps {
  onSuccess: (user: { email: string; name: string }) => void;
}

export function AuthView({ onSuccess }: AuthViewProps) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [errors, setErrors] = useState<{ email?: string; password?: string; confirmPassword?: string }>({});

  const validate = () => {
    const errs: typeof errors = {};
    if (!email) {
      errs.email = "Email address is required.";
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      errs.email = "Please enter a valid email address.";
    }

    if (!password) {
      errs.password = "Password is required.";
    } else if (password.length < 8) {
      errs.password = "Password must be at least 8 characters.";
    }

    if (mode === "signup" && password !== confirmPassword) {
      errs.confirmPassword = "Passwords do not match.";
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      onSuccess({
        email,
        name: email.split("@")[0] || "Developer",
      });
    }
  };

  const handleDemoSignIn = () => {
    onSuccess({
      email: "developer@stackpilot.ai",
      name: "Alex Developer",
    });
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#070a12] p-4 relative overflow-hidden select-none">
      {/* Glow Backdrop */}
      <div className="absolute top-1/4 -left-20 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 -right-20 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md bg-surface/80 border border-slate-800 rounded-2xl p-8 backdrop-blur-2xl shadow-2xl relative z-10 space-y-6">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-indigo-600 via-primary-500 to-cyan-400 p-[1px] shadow-glow flex items-center justify-center">
            <div className="h-full w-full bg-[#090d16] rounded-2xl flex items-center justify-center">
              <Cpu className="h-6 w-6 text-indigo-400" />
            </div>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">STACKPILOT</h1>
          <p className="text-xs text-slate-400">
            {mode === "login"
              ? "Sign in to access your codebase intelligence workspace"
              : "Create an account to start building with agentic AI"}
          </p>
        </div>

        {/* OAuth Buttons */}
        <div className="space-y-2.5">
          <button
            onClick={handleDemoSignIn}
            className="w-full py-2.5 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-white font-medium text-xs flex items-center justify-center gap-2.5 transition-colors shadow-sm"
          >
            <Github className="h-4 w-4" />
            <span>Continue with GitHub</span>
          </button>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-[1px] bg-slate-800" />
          <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">Or with email</span>
          <div className="flex-1 h-[1px] bg-slate-800" />
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email */}
          <div className="space-y-1.5 text-left">
            <label className="text-[11px] font-semibold text-slate-300">Email Address</label>
            <div className="relative">
              <Mail className="h-4 w-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="developer@company.com"
                className={`w-full bg-slate-900/90 border rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder:text-slate-600 outline-none transition-colors ${
                  errors.email ? "border-rose-500" : "border-slate-800 focus:border-indigo-500"
                }`}
              />
            </div>
            {errors.email && (
              <p className="text-[11px] text-rose-400 flex items-center gap-1 mt-1">
                <AlertCircle className="h-3 w-3" /> {errors.email}
              </p>
            )}
          </div>

          {/* Password */}
          <div className="space-y-1.5 text-left">
            <label className="text-[11px] font-semibold text-slate-300">Password</label>
            <div className="relative">
              <Lock className="h-4 w-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className={`w-full bg-slate-900/90 border rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder:text-slate-600 outline-none transition-colors ${
                  errors.password ? "border-rose-500" : "border-slate-800 focus:border-indigo-500"
                }`}
              />
            </div>
            {errors.password && (
              <p className="text-[11px] text-rose-400 flex items-center gap-1 mt-1">
                <AlertCircle className="h-3 w-3" /> {errors.password}
              </p>
            )}
          </div>

          {/* Confirm Password (Signup only) */}
          {mode === "signup" && (
            <div className="space-y-1.5 text-left">
              <label className="text-[11px] font-semibold text-slate-300">Confirm Password</label>
              <div className="relative">
                <Lock className="h-4 w-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className={`w-full bg-slate-900/90 border rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder:text-slate-600 outline-none transition-colors ${
                    errors.confirmPassword ? "border-rose-500" : "border-slate-800 focus:border-indigo-500"
                  }`}
                />
              </div>
              {errors.confirmPassword && (
                <p className="text-[11px] text-rose-400 flex items-center gap-1 mt-1">
                  <AlertCircle className="h-3 w-3" /> {errors.confirmPassword}
                </p>
              )}
            </div>
          )}

          {/* Remember Me & Forgot Password */}
          <div className="flex items-center justify-between text-xs pt-1">
            <label className="flex items-center gap-2 cursor-pointer select-none text-slate-400 hover:text-slate-300">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
              />
              <span>Remember me</span>
            </label>

            {mode === "login" && (
              <span className="text-indigo-400 hover:text-indigo-300 cursor-pointer">
                Forgot password?
              </span>
            )}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition-colors shadow-glow flex items-center justify-center gap-2"
          >
            <span>{mode === "login" ? "Sign In to STACKPILOT" : "Create Account"}</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </form>

        {/* Toggle Mode */}
        <div className="text-center text-xs text-slate-400 pt-2 border-t border-slate-800/80">
          {mode === "login" ? (
            <span>
              Don&apos;t have an account?{" "}
              <button
                onClick={() => {
                  setMode("signup");
                  setErrors({});
                }}
                className="text-indigo-400 hover:text-indigo-300 font-semibold"
              >
                Sign up
              </button>
            </span>
          ) : (
            <span>
              Already have an account?{" "}
              <button
                onClick={() => {
                  setMode("login");
                  setErrors({});
                }}
                className="text-indigo-400 hover:text-indigo-300 font-semibold"
              >
                Sign in
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
