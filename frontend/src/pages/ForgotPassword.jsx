import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, MailCheck } from "lucide-react";
import { toast } from "sonner";
import { api, describeApiError } from "@/lib/apiClient";
import { BrandLogo } from "@/components/BrandLogo";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    try {
      const res = await api.post("/auth/forgot-password", { email: email.trim() });
      setSent(true);
      toast.success(res.data.message);
    } catch (err) {
      toast.error(describeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#eef3f7] flex items-stretch justify-center md:items-center md:py-10 font-nunito">
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-[440px] bg-white md:rounded-3xl md:shadow-[0_20px_60px_rgba(22,65,148,0.12)] px-6 pt-6 pb-12 md:px-10"
      >
        <Link
          to="/"
          data-testid="back-link"
          className="absolute left-5 top-5 flex items-center gap-1 text-[#17334d] hover:text-[#164194] font-semibold"
        >
          <ArrowLeft size={22} /> Retour
        </Link>

        <div className="pt-10 pb-2">
          <BrandLogo markSize={58} />
        </div>

        <div className="mt-4 rounded-2xl border border-[#e3e9ef] px-5 py-7 md:px-7">
          {sent ? (
            <div className="text-center py-6" data-testid="reset-sent">
              <MailCheck size={56} className="mx-auto text-[#1aa3dd] mb-4" />
              <h1 className="text-[#17334d] font-extrabold text-2xl mb-3">E-mail envoyé</h1>
              <p className="text-[#5a6b7a] text-base">
                Si un compte existe pour <strong>{email}</strong>, vous recevrez un lien de
                réinitialisation de votre mot de passe.
              </p>
            </div>
          ) : (
            <>
              <h1 className="text-center text-[#17334d] font-extrabold text-3xl mb-2">
                Mot de passe oublié ?
              </h1>
              <p className="text-center text-[#5a6b7a] text-base mb-6">
                Saisissez votre identifiant pour recevoir un lien de réinitialisation.
              </p>
              <form onSubmit={onSubmit}>
                <label htmlFor="email" className="block text-[#17334d] font-bold text-lg mb-2">
                  Identifiant (n°mobile, e-mail ...) <span className="text-[#e45c1e]">*</span>
                </label>
                <input
                  id="email"
                  data-testid="forgot-email-input"
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3.5 text-[#17334d] text-lg transition-colors mb-6"
                />
                <button
                  type="submit"
                  data-testid="forgot-submit"
                  disabled={loading}
                  className="w-full rounded-full bg-[#c4521f] hover:bg-[#a9441a] active:scale-[0.99] text-white font-extrabold text-xl py-4 transition-all disabled:opacity-60 shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
                >
                  {loading ? "Envoi..." : "Recevoir le lien"}
                </button>
              </form>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
