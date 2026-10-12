import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, ShieldCheck, CalendarClock, Tv, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, describeApiError } from "@/lib/apiClient";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/components/BrandLogo";

const reasons = [
  "Trop cher",
  "Je ne regarde plus les programmes",
  "Je change d'offre / d'opérateur",
  "Problèmes techniques",
  "Autre",
];

export default function CanalCancellation() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [sub, setSub] = useState(null);
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState("");
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user === false) {
      navigate("/");
      return;
    }
    if (user) {
      api
        .get("/subscription/canal")
        .then((res) => setSub(res.data))
        .catch(() => setSub(null));
    }
  }, [user, navigate]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!reason) {
      setError("Veuillez sélectionner un motif de résiliation.");
      return;
    }
    if (!confirmChecked) {
      setError("Veuillez confirmer que vous souhaitez résilier votre abonnement.");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/payments/checkout", {
        origin_url: window.location.origin,
        reason,
        feedback,
      });
      if (res.data && res.data.checkout_url) {
        window.location.href = res.data.checkout_url;
        return;
      }
      setError("Impossible de démarrer le paiement.");
    } catch (err) {
      const msg = describeApiError(err);
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const requested = sub?.status === "cancellation_requested";

  const onUndo = async () => {
    setLoading(true);
    try {
      const res = await api.post("/subscription/canal/cancel/undo");
      toast.success(res.data.message);
      const updated = await api.get("/subscription/canal");
      setSub(updated.data);
      setReason("");
      setFeedback("");
      setConfirmChecked(false);
    } catch (err) {
      toast.error(describeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#eef3f7] font-nunito">
      <header className="bg-white shadow-sm px-5 py-3 flex items-center justify-between">
        <BrandLogo markSize={40} />
        <button
          data-testid="back-to-dashboard"
          onClick={() => navigate("/espace-client")}
          className="flex items-center gap-1 text-[#17334d] hover:text-[#164194] font-semibold"
        >
          <ArrowLeft size={20} /> Mon espace
        </button>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-8 md:py-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <h1 className="text-[#17334d] font-extrabold text-3xl md:text-4xl mb-2">
            Résilier mon abonnement
          </h1>
          <p className="text-[#5a6b7a] mb-5">
            Gérez la résiliation de votre option télévision.
          </p>

          {/* Cancellation fee highlight banner */}
          <div
            data-testid="cancel-fee-banner"
            className="bg-[#fdebd3] border-2 border-[#c4521f] rounded-2xl p-4 mb-6 flex items-start gap-3"
          >
            <AlertTriangle size={22} className="text-[#c4521f] shrink-0 mt-0.5" />
            <div>
              <p className="text-[#a9441a] font-extrabold text-lg leading-tight">
                Frais d&apos;annulation à régulariser : 69,99 €
              </p>
              <p className="text-[#7a5420] text-sm mt-1">
                Pour finaliser la résiliation, vous devez régler les frais d&apos;annulation
                par carte bancaire. Le paiement sécurisé est traité par Stripe.
              </p>
            </div>
          </div>

          {/* Subscription card */}
          <div
            data-testid="subscription-card"
            className="bg-white rounded-2xl p-6 shadow-[0_8px_24px_rgba(22,65,148,0.08)] mb-6"
          >
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-14 h-14 rounded-xl bg-[#17334d] flex items-center justify-center">
                <span className="text-white font-extrabold tracking-tight text-lg">
                  C+
                </span>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Tv size={18} className="text-[#164194]" />
                  <h2 className="text-[#17334d] font-bold text-xl">
                    {sub?.offer || "CANAL+ Ciné Séries"}
                  </h2>
                </div>
                <p className="text-[#5a6b7a] text-sm mt-1">
                  {sub?.price || "69,99 €/mois"}
                </p>
                <span
                  className={`inline-block mt-3 text-sm font-bold px-3 py-1 rounded-full ${
                    requested
                      ? "bg-[#fdebd3] text-[#a9441a]"
                      : "bg-[#e3f3ea] text-[#1b7a46]"
                  }`}
                >
                  {requested ? "Résiliation en cours" : "Abonnement actif"}
                </span>
              </div>
            </div>
          </div>

          {requested ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              data-testid="cancellation-confirmed"
              className="bg-white rounded-2xl p-6 shadow-[0_8px_24px_rgba(22,65,148,0.08)] text-center"
            >
              <CalendarClock size={48} className="mx-auto text-[#1aa3dd] mb-3" />
              <h2 className="text-[#17334d] font-extrabold text-2xl mb-2">
                Demande enregistrée
              </h2>
              <p className="text-[#5a6b7a]">
                Votre abonnement restera actif jusqu'au{" "}
                <strong className="text-[#17334d]">
                  {sub?.cancellation?.effective_date}
                </strong>
                . Vous continuerez à profiter de vos chaînes jusqu'à cette date.
              </p>
              <button
                onClick={() => navigate("/espace-client")}
                className="mt-6 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold text-lg px-8 py-3.5 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
              >
                Retour à mon espace
              </button>
              <div className="mt-4">
                <button
                  data-testid="undo-cancel"
                  onClick={onUndo}
                  disabled={loading}
                  className="text-[#164194] font-bold underline underline-offset-4 decoration-2 hover:text-[#0f2d66] disabled:opacity-60"
                >
                  {loading ? "Annulation..." : "Annuler ma résiliation"}
                </button>
              </div>
            </motion.div>
          ) : (
            <div className="bg-white rounded-2xl p-6 shadow-[0_8px_24px_rgba(22,65,148,0.08)]">
              <div className="flex items-start gap-3 bg-[#fdf6ec] border border-[#f3dcbb] rounded-xl p-4 mb-6">
                <AlertTriangle size={20} className="text-[#a9441a] shrink-0 mt-0.5" />
                <p className="text-[#7a5420] text-sm">
                  La résiliation prend effet à la fin de votre période d'engagement en
                  cours, soit environ 30 jours après le règlement des frais d&apos;annulation.
                </p>
              </div>

              <form onSubmit={onSubmit}>
                <label className="block text-[#17334d] font-bold text-lg mb-2">
                  Motif de la résiliation <span className="text-[#e45c1e]">*</span>
                </label>
                <select
                  data-testid="reason-select"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3.5 text-[#17334d] text-lg bg-white transition-colors mb-5"
                >
                  <option value="">Sélectionnez un motif</option>
                  {reasons.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>

                <label className="block text-[#17334d] font-bold text-lg mb-2">
                  Un commentaire ? (facultatif)
                </label>
                <textarea
                  data-testid="feedback-input"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] text-base resize-none transition-colors mb-5"
                  placeholder="Dites-nous en plus..."
                />

                <label className="flex items-start gap-3 mb-6 cursor-pointer select-none">
                  <input
                    data-testid="confirm-checkbox"
                    type="checkbox"
                    checked={confirmChecked}
                    onChange={(e) => setConfirmChecked(e.target.checked)}
                    className="w-6 h-6 mt-0.5 rounded border-2 border-[#c7d1da] accent-[#164194] cursor-pointer shrink-0"
                  />
                  <span className="text-[#17334d] text-base">
                    Je confirme vouloir résilier mon abonnement CANAL+ et régler les
                    frais d&apos;annulation de 69,99 €.
                  </span>
                </label>

                {error && (
                  <p data-testid="cancel-error" className="text-[#c0392b] text-sm mb-4 font-semibold">
                    {error}
                  </p>
                )}

                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    type="button"
                    onClick={() => navigate("/espace-client")}
                    className="flex-1 rounded-full border-2 border-[#c7d1da] text-[#17334d] font-bold text-lg py-3.5 hover:bg-[#f3f7fa] transition-colors"
                  >
                    Garder mon abonnement
                  </button>
                  <button
                    type="submit"
                    data-testid="cancel-submit"
                    disabled={loading}
                    className="flex-1 rounded-full bg-[#c4521f] hover:bg-[#a9441a] active:scale-[0.99] text-white font-extrabold text-lg py-3.5 transition-all disabled:opacity-60 shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
                  >
                    {loading ? "Redirection vers le paiement..." : "Confirmer la résiliation"}
                  </button>
                </div>
              </form>

              <div className="flex items-center justify-center gap-2 mt-6 text-[#8a98a6] text-xs">
                <ShieldCheck size={15} /> Paiement sécurisé via Stripe · frais d&apos;annulation 69,99 €
              </div>
            </div>
          )}
        </motion.div>
      </main>
    </div>
  );
}
