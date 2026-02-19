import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sparkles, LogIn, Loader2, Eye, EyeOff, Shield, FileText, Code2, TestTube } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
import loginBg from "@/assets/images/login-bg.jpg";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login } = useAuth();
  const { toast } = useToast();

  useEffect(() => {
    document.title = "Login | DocuGen AI";
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setIsSubmitting(true);
    try {
      await login(email.trim(), password);
      toast({ title: "Welcome back", description: "Successfully signed in" });
    } catch (err: any) {
      const msg = err.message?.includes("401")
        ? "Invalid email or password"
        : err.message?.includes("400")
          ? "Please fill in all fields"
          : "Login failed. Please try again.";
      toast({ title: "Login failed", description: msg, variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  };

  const features = [
    { icon: FileText, text: "Auto-generate BRDs & documentation" },
    { icon: Code2, text: "AI-powered code generation" },
    { icon: TestTube, text: "Smart test case & data generation" },
    { icon: Shield, text: "Security analysis & JIRA sync" },
  ];

  return (
    <div className="min-h-screen flex">
      <div
        className="hidden lg:flex lg:w-[55%] relative items-center justify-center"
        style={{
          backgroundImage: `url(${loginBg})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-black/80 via-black/60 to-black/80" />
        <div className="relative z-10 max-w-lg px-12">
          <div className="flex items-center gap-3 mb-8">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/90 backdrop-blur-sm">
              <Sparkles className="h-6 w-6 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-white tracking-tight">DocuGen AI</h1>
              <p className="text-sm text-blue-200/80">Intelligent SDLC Platform</p>
            </div>
          </div>
          <p className="text-lg text-gray-200 leading-relaxed mb-10">
            Transform your software development lifecycle with AI-powered documentation, requirements analysis, and code generation.
          </p>
          <div className="space-y-4">
            {features.map((f, i) => (
              <div key={i} className="flex items-center gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/10 backdrop-blur-sm border border-white/10">
                  <f.icon className="h-5 w-5 text-blue-300" />
                </div>
                <span className="text-gray-200 text-sm">{f.text}</span>
              </div>
            ))}
          </div>
          <div className="mt-12 pt-8 border-t border-white/10">
            <p className="text-xs text-gray-400">Powered by PWC GenAI &middot; Gemini 2.0 Flash</p>
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-background p-6">
        <div className="w-full max-w-[400px]">
          <div className="flex flex-col items-center mb-8 lg:hidden">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary mb-4">
              <Sparkles className="h-7 w-7 text-primary-foreground" />
            </div>
            <h1 className="text-2xl font-bold" data-testid="text-app-title">DocuGen AI</h1>
            <p className="text-sm text-muted-foreground mt-1">Intelligent SDLC Platform</p>
          </div>

          <div className="hidden lg:block mb-10">
            <h2 className="text-3xl font-bold tracking-tight" data-testid="text-app-title">Welcome back</h2>
            <p className="text-muted-foreground mt-2">Sign in to your account to continue</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-sm font-medium">Email address</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                autoComplete="email"
                autoFocus
                className="h-11"
                data-testid="input-email"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-sm font-medium">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  className="pr-10 h-11"
                  data-testid="input-password"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  data-testid="button-toggle-password"
                >
                  {showPassword ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-muted-foreground" />}
                </Button>
              </div>
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full"
              disabled={isSubmitting || !email.trim() || !password}
              data-testid="button-login"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Signing in...
                </>
              ) : (
                "Sign In"
              )}
            </Button>
          </form>

          <div className="flex items-center gap-3 mt-8">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-muted-foreground">Need access?</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <p className="text-xs text-muted-foreground text-center mt-4">
            Contact your administrator for account access
          </p>
        </div>
      </div>
    </div>
  );
}
