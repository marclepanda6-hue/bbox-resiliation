import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { api, describeApiError } from "@/lib/apiClient";
import { BrandLogo } from "@/components/BrandLogo";

const MAX_POLLS = 15;
const POLL_INTERVAL = 2000;

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [state, setState] = useState("polling"); // polling | paid | timeout | error
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!sessionId) {
      setState("error");
      setErrorMsg("Session de paiement manquante.");
      return;
    }
    let attempts = 0;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await api.get(`/payments/status/${sessionId}`);
        if (cancelled) return;
        if (res.data.payment_status === "paid") {
          setState("paid");
          return;
        }
        attempts += 1;
        if (attempts >= MAX_POLLS) {
          setState("timeout");
          return;
        }
        setTimeout(poll, POLL_INTERVAL);
      } catch (err) {
        if (cancelled) return;
        setErrorMsg(describeApiError(err));
        setState("error");
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <div className="min-h-screen w-full bg-[#eef3f7] font-nunito flex flex-col">
      <header className="bg-white shadow-sm px-5 py-3">
        <BrandLogo markSize={40} />
      </header>
      <main className="flex-1 flex items-center justify-center px-5 py-10">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white rounded-2xl shadow-[0_8px_24px_rgba(22,65,148,0.08)] p-8 max-w-lg w-full text-center"
        >
          {state === "polling" && (
            <>
              <Loader2 size={56} className="mx-auto text-[#164194] mb-4 animate-spin" />
              <h1 className="text-[#17334d] font-extrabold text-2xl mb-2">
                Validation de votre paiement...
              </h1>
              <p className="text-[#5a6b7a]">
                Nous confirmons le règlement des frais d&apos;annulation. Merci de patienter.
              </p>
            </>
          )}
          {state === "paid" && (
            <>
              <CheckCircle2 size={64} className="mx-auto text-[#1b7a46] mb-4" />
              <h1 className="text-[#17334d] font-extrabold text-2xl mb-2">
                Frais d&apos;annulation réglés
              </h1>
              <p className="text-[#5a6b7a] mb-6">
                Votre résiliation CANAL+ Ciné Séries est désormais enregistrée. Elle
                prendra effet à la fin de votre période d&apos;engagement (environ 30 jours).
              </p>
              <button
                data-testid="back-to-dashboard"
                onClick={() => navigate("/espace-client")}
                className="rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold px-8 py-3.5 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
              >
                Retour à mon espace
              </button>
            </>
          )}
          {state === "timeout" && (
            <>
              <AlertCircle size={56} className="mx-auto text-[#c4521f] mb-4" />
              <h1 className="text-[#17334d] font-extrabold text-2xl mb-2">
                Paiement en cours de validation
              </h1>
              <p className="text-[#5a6b7a] mb-6">
                Votre paiement est encore en cours de traitement par Stripe. Rechargez
                cette page dans quelques instants ou retournez à votre espace.
              </p>
              <button
                onClick={() => navigate("/espace-client")}
                className="rounded-full border-2 border-[#164194] text-[#164194] font-bold px-8 py-3 hover:bg-[#164194] hover:text-white transition-colors"
              >
                Retour à mon espace
              </button>
            </>
          )}
          {state === "error" && (
            <>
              <AlertCircle size={56} className="mx-auto text-[#c0392b] mb-4" />
              <h1 className="text-[#17334d] font-extrabold text-2xl mb-2">
                Impossible de vérifier le paiement
              </h1>
              <p className="text-[#c0392b] mb-6">{errorMsg || "Erreur inconnue."}</p>
              <button
                onClick={() => navigate("/espace-client")}
                className="rounded-full border-2 border-[#164194] text-[#164194] font-bold px-8 py-3 hover:bg-[#164194] hover:text-white transition-colors"
              >
                Retour à mon espace
              </button>
            </>
          )}
        </motion.div>
      </main>
    </div>
  );
}
