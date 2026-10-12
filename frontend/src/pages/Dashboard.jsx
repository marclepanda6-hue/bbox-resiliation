import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { LogOut, User, Landmark, Tv, CalendarClock, Shield } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/apiClient";
import { BrandLogo } from "@/components/BrandLogo";

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
  } catch {
    return iso;
  }
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [prelevements, setPrelevements] = useState(null);

  useEffect(() => {
    if (user === false) navigate("/");
    if (user) {
      api.get("/prelevements").then((r) => setPrelevements(r.data)).catch(() => setPrelevements(null));
    }
  }, [user, navigate]);

  if (!user) {
    return (
      <div className="min-h-screen bg-[#eef3f7] flex items-center justify-center font-nunito text-[#17334d]">
        Chargement...
      </div>
    );
  }

  const isAdmin = user.role === "admin";
  const fullName = user.name || "Non renseigné";
  const latestDate = prelevements?.latest;

  return (
    <div className="min-h-screen w-full bg-[#eef3f7] font-nunito">
      <header className="bg-white shadow-sm px-5 py-3 flex items-center justify-between">
        <BrandLogo markSize={40} />
        <div className="flex items-center gap-3">
          {isAdmin && (
            <button
              data-testid="goto-admin"
              onClick={() => navigate("/admin/profils")}
              className="flex items-center gap-1.5 text-[#164194] font-semibold hover:text-[#0f2d66] transition-colors"
            >
              <Shield size={18} /> Admin
            </button>
          )}
          <button
            data-testid="logout-button"
            onClick={async () => {
              await logout();
              navigate("/");
            }}
            className="flex items-center gap-2 text-[#17334d] font-semibold hover:text-[#c4521f] transition-colors"
          >
            <LogOut size={20} /> Déconnexion
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-8 md:py-12">
        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-[#17334d] font-extrabold text-3xl md:text-4xl"
        >
          Mon espace client
        </motion.h1>
        <p className="text-[#5a6b7a] mt-2 mb-8" data-testid="dashboard-welcome">
          Bienvenue {user.name || user.email || user.phone}, voici le récapitulatif de votre compte.
        </p>

        <div className="grid sm:grid-cols-2 gap-4">
          {/* Titulaire */}
          <motion.section
            data-testid="section-titulaire"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)]"
          >
            <div className="w-11 h-11 rounded-full bg-[#1aa3dd]/10 flex items-center justify-center mb-3">
              <User size={22} className="text-[#164194]" />
            </div>
            <h2 className="text-[#8a98a6] font-semibold text-sm uppercase tracking-wide">
              Titulaire du compte
            </h2>
            <p className="text-[#17334d] font-bold text-xl mt-1" data-testid="full-name">
              {fullName}
            </p>
          </motion.section>

          {/* IBAN */}
          <motion.section
            data-testid="section-iban"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)]"
          >
            <div className="w-11 h-11 rounded-full bg-[#1aa3dd]/10 flex items-center justify-center mb-3">
              <Landmark size={22} className="text-[#164194]" />
            </div>
            <h2 className="text-[#8a98a6] font-semibold text-sm uppercase tracking-wide">
              Coordonnées bancaires
            </h2>
            <p className="text-[#17334d] font-bold text-xl mt-1 tracking-wider" data-testid="iban-masked">
              {user.has_iban ? user.iban_masked : "Non renseigné"}
            </p>
            <p className="text-[#8a98a6] text-xs mt-1">Masqué pour des raisons de confidentialité</p>
          </motion.section>

          {/* Forfait */}
          <motion.section
            data-testid="section-forfait"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)]"
          >
            <div className="w-11 h-11 rounded-xl bg-[#17334d] flex items-center justify-center mb-3">
              <span className="text-white font-extrabold text-sm">C+</span>
            </div>
            <h2 className="text-[#8a98a6] font-semibold text-sm uppercase tracking-wide">Mon forfait</h2>
            <div className="flex items-center gap-2 mt-1">
              <Tv size={18} className="text-[#164194]" />
              <p className="text-[#17334d] font-bold text-xl">CANAL+ Ciné Séries</p>
            </div>
            <p className="text-[#5a6b7a] mt-1 font-semibold">69,99 €/mois</p>
            <button
              data-testid="goto-cancel-canal"
              onClick={() => navigate("/resiliation-canal")}
              className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] active:scale-[0.99] text-white font-extrabold text-base py-3 px-4 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
            >
              Résilier mon abonnement
            </button>
          </motion.section>

          {/* Prélèvement */}
          <motion.section
            data-testid="section-prelevement"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)]"
          >
            <div className="w-11 h-11 rounded-full bg-[#1aa3dd]/10 flex items-center justify-center mb-3">
              <CalendarClock size={22} className="text-[#164194]" />
            </div>
            <h2 className="text-[#8a98a6] font-semibold text-sm uppercase tracking-wide">
              Date de prélèvement
            </h2>
            <p className="text-[#17334d] font-bold text-xl mt-1" data-testid="prelevement-date">
              {formatDate(latestDate)}
            </p>
            <p className="text-[#5a6b7a] mt-1 font-semibold" data-testid="prelevement-amount">
              Montant : 69,99 €
            </p>
            {prelevements?.count > 0 && (
              <p className="text-[#8a98a6] text-xs mt-1">
                {prelevements.count} prélèvement{prelevements.count > 1 ? "s" : ""} enregistré
                {prelevements.count > 1 ? "s" : ""}
              </p>
            )}
          </motion.section>
        </div>

        {/* Historique des prélèvements */}
        {prelevements?.prelevements?.length > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)] mt-4"
          >
            <h2 className="text-[#17334d] font-bold text-lg mb-3">Historique des prélèvements</h2>
            <ul className="divide-y divide-[#eef3f7]">
              {prelevements.prelevements.slice(0, 8).map((p, i) => (
                <li key={i} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-[#17334d] font-semibold">{p.label}</p>
                    <p className="text-[#8a98a6] text-sm">{formatDate(p.date)}</p>
                  </div>
                  <span className="text-[#17334d] font-bold">
                    {p.amount.toFixed(2).replace(".", ",")} €
                  </span>
                </li>
              ))}
            </ul>
          </motion.section>
        )}
      </main>
    </div>
  );
}
