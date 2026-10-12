import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { describeApiError } from "@/lib/apiClient";
import { BrandLogo } from "@/components/BrandLogo";

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [identifiant, setIdentifiant] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!identifiant.trim() || !password) {
      setError("Veuillez renseigner tous les champs obligatoires.");
      return;
    }
    setLoading(true);
    try {
      const data = await login(identifiant.trim(), password);
      toast.success(data.message || "Connexion réussie");
      navigate("/espace-client");
    } catch (err) {
      const msg = describeApiError(err, "Erreur de connexion");
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#eef3f7] flex items-stretch justify-center md:items-center md:py-10 font-nunito">
      {/* "Votre avis" side tab */}
      <button
        data-testid="avis-tab"
        className="hidden sm:flex fixed right-0 top-1/2 -translate-y-1/2 z-20 bg-white shadow-[-2px_0_12px_rgba(0,0,0,0.08)] rounded-l-xl px-2 py-6 items-center justify-center hover:px-3 transition-all"
        style={{ writingMode: "vertical-rl" }}
      >
        <span className="text-[#17334d] font-semibold text-sm tracking-wide rotate-180">
          Votre avis
        </span>
      </button>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-[440px] bg-white md:rounded-3xl md:shadow-[0_20px_60px_rgba(22,65,148,0.12)] px-6 pt-6 pb-12 md:px-10"
      >
        {/* Close button hidden per product decision */}

        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="pt-6 pb-2"
        >
          <BrandLogo markSize={58} />
        </motion.div>

        {/* Inner card */}
        <div className="mt-4 rounded-2xl border border-[#e3e9ef] px-5 py-7 md:px-7">
          <div className="text-center text-[2.4rem] leading-none mb-2 select-none" aria-hidden="true">
            👋
          </div>
          <h1 className="text-center text-[#17334d] font-extrabold text-3xl md:text-[2rem] mb-6">
            Heureux de vous retrouver
          </h1>

          <p className="text-[#17334d] text-sm mb-5">
            <span className="text-[#e45c1e]">*</span> champs obligatoires
          </p>

          <form onSubmit={onSubmit} noValidate>
            {/* Identifiant */}
            <label htmlFor="identifiant" className="block text-[#17334d] font-bold text-lg mb-2">
              Identifiant (n°mobile, e-mail ...) <span className="text-[#e45c1e]">*</span>
            </label>
            <input
              id="identifiant"
              data-testid="identifiant-input"
              type="text"
              value={identifiant}
              onChange={(e) => setIdentifiant(e.target.value)}
              placeholder="email ou numéro de téléphone"
              className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3.5 text-[#17334d] text-lg transition-colors"
              autoComplete="username"
            />
            <Link
              to="/retrouver-identifiant"
              data-testid="find-identifiant-link"
              className="inline-block mt-3 mb-6 text-[#17334d] font-semibold underline underline-offset-4 decoration-2 hover:text-[#164194]"
            >
              Comment retrouver mon identifiant ?
            </Link>

            {/* Mot de passe */}
            <label htmlFor="password" className="block text-[#17334d] font-bold text-lg mb-2">
              Mot de passe <span className="text-[#e45c1e]">*</span>
            </label>
            <div className="relative">
              <input
                id="password"
                data-testid="password-input"
                type={showPwd ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3.5 pr-12 text-[#17334d] text-lg transition-colors"
                autoComplete="current-password"
              />
              <button
                type="button"
                data-testid="toggle-password"
                onClick={() => setShowPwd((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#17334d] hover:text-[#164194] transition-colors"
                aria-label={showPwd ? "Masquer le mot de passe" : "Afficher le mot de passe"}
              >
                {showPwd ? <EyeOff size={24} /> : <Eye size={24} />}
              </button>
            </div>
            <Link
              to="/mot-de-passe-oublie"
              data-testid="forgot-password-link"
              className="inline-block mt-3 mb-5 text-[#17334d] font-semibold underline underline-offset-4 decoration-2 hover:text-[#164194]"
            >
              Mot de passe oublié ?
            </Link>

            {/* Remember */}
            <label className="flex items-center gap-3 mb-6 cursor-pointer select-none">
              <input
                data-testid="remember-checkbox"
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="w-6 h-6 rounded border-2 border-[#c7d1da] accent-[#164194] cursor-pointer"
              />
              <span className="text-[#17334d] text-lg">Se souvenir de moi</span>
            </label>

            {error && (
              <p data-testid="login-error" className="text-[#c0392b] text-sm mb-4 font-semibold">
                {error}
              </p>
            )}

            <button
              type="submit"
              data-testid="login-submit"
              disabled={loading}
              className="w-full rounded-full bg-[#c4521f] hover:bg-[#a9441a] active:scale-[0.99] text-white font-extrabold text-xl py-4 transition-all disabled:opacity-60 shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
            >
              {loading ? "Connexion..." : "Me connecter"}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}
