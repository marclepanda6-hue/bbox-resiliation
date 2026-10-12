import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { XCircle, AlertTriangle } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";

export default function PaymentCancel() {
  const navigate = useNavigate();
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
          <XCircle size={64} className="mx-auto text-[#c4521f] mb-4" />
          <h1 className="text-[#17334d] font-extrabold text-2xl mb-2">
            Paiement annulé
          </h1>
          <p className="text-[#5a6b7a] mb-4">
            Vous avez interrompu le paiement. Votre résiliation CANAL+ Ciné Séries
            n&apos;est pas effective tant que les frais d&apos;annulation ne sont pas réglés.
          </p>
          <div className="bg-[#fdebd3] border border-[#c4521f] rounded-xl p-3 mb-6 flex items-start gap-2 text-left">
            <AlertTriangle size={18} className="text-[#c4521f] shrink-0 mt-0.5" />
            <p className="text-[#7a5420] text-sm">
              Pour finaliser la résiliation, relancez la démarche et acquittez les
              frais d&apos;annulation de 69,99 €.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              data-testid="back-to-dashboard"
              onClick={() => navigate("/espace-client")}
              className="rounded-full border-2 border-[#c7d1da] text-[#17334d] font-bold px-6 py-3 hover:bg-[#f3f7fa] transition-colors"
            >
              Retour à mon espace
            </button>
            <button
              data-testid="retry-cancel"
              onClick={() => navigate("/resiliation-canal")}
              className="rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold px-6 py-3 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
            >
              Reprendre la résiliation
            </button>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
