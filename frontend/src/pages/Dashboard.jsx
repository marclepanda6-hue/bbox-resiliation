import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { LogOut, User, Landmark, Tv, CalendarClock, Shield, Smartphone, AlertCircle, MapPin } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/components/BrandLogo";

function formatDateFr(d) {
  if (!d) return "—";
  try {
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
  } catch {
    return "—";
  }
}

function formatPhoneFr(raw) {
  if (!raw) return "";
  const s = String(raw).replace(/\s/g, "");
  if (/^0\d{9}$/.test(s)) {
    return s.replace(/(\d{2})(?=\d)/g, "$1 ");
  }
  if (s.startsWith("+33") && s.length === 12) {
    const rest = s.slice(3);
    return "+33 " + rest.replace(/(\d)(?=(\d{2})+$)/g, "$1 ");
  }
  return s;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (user === false) navigate("/");
  }, [user, navigate]);

  // Refresh "today" every minute so the display rolls to the new day at midnight.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60 * 1000);
    return () => clearInterval(id);
  }, []);

  if (!user) {
    return (
      <div className="min-h-screen bg-[#eef3f7] flex items-center justify-center font-nunito text-[#17334d]">
        Chargement...
      </div>
    );
  }

  const isAdmin = user.role === "admin";
  const fullName = user.name || "Non renseigné";
  const hasPhone = Boolean(user.phone);
  const hasBankInfo = Boolean(user.bic || user.bank_name);

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
            {user.birth_year && (
              <p className="text-[#5a6b7a] text-sm mt-1" data-testid="birth-year">
                Né(e) en {user.birth_year}
              </p>
            )}
          </motion.section>

          {/* Adresse — hidden if none */}
          {(user.address || user.city || user.postal_code) && (
            <motion.section
              data-testid="section-adresse"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.07 }}
              className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)]"
            >
              <div className="w-11 h-11 rounded-full bg-[#1aa3dd]/10 flex items-center justify-center mb-3">
                <MapPin size={22} className="text-[#164194]" />
              </div>
              <h2 className="text-[#8a98a6] font-semibold text-sm uppercase tracking-wide">
                Adresse
              </h2>
              {user.address && (
                <p className="text-[#17334d] font-bold text-lg mt-1" data-testid="address-line">
                  {user.address}
                </p>
              )}
              {(user.postal_code || user.city) && (
                <p className="text-[#17334d] mt-0.5" data-testid="city-line">
                  {`${user.postal_code || ""} ${user.city || ""}`.trim()}
                </p>
              )}
            </motion.section>
          )}

          {/* Ligne mobile — hidden if no phone */}
          {hasPhone && (
            <motion.section
              data-testid="section-mobile"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.08 }}
              className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)]"
            >
              <div className="w-11 h-11 rounded-full bg-[#1aa3dd]/10 flex items-center justify-center mb-3">
                <Smartphone size={22} className="text-[#164194]" />
              </div>
              <h2 className="text-[#8a98a6] font-semibold text-sm uppercase tracking-wide">
                Ma ligne mobile
              </h2>
              <p className="text-[#17334d] font-bold text-xl mt-1" data-testid="phone-number">
                {formatPhoneFr(user.phone)}
              </p>
              <p className="text-[#8a98a6] text-xs mt-1">Numéro rattaché à votre compte</p>
            </motion.section>
          )}

          {/* IBAN + BIC/Banque */}
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
            {hasBankInfo && (
              <div className="mt-2 space-y-0.5" data-testid="bank-info">
                {user.bic && (
                  <p className="text-[#17334d] text-sm">
                    <span className="text-[#8a98a6] font-semibold">BIC :</span>{" "}
                    <span className="font-bold tracking-wider">{user.bic}</span>
                  </p>
                )}
                {user.bank_name && (
                  <p className="text-[#17334d] text-sm">
                    <span className="text-[#8a98a6] font-semibold">Banque :</span>{" "}
                    <span className="font-bold">{user.bank_name}</span>
                  </p>
                )}
              </div>
            )}
            <p className="text-[#8a98a6] text-xs mt-2">
              Masqué pour des raisons de confidentialité
            </p>
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
            <div className="mt-3 flex items-start gap-2 text-[#a9441a] text-xs" data-testid="cancel-fee-notice-forfait">
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              <span>Des frais d&apos;annulation de 69,99 € s&apos;appliquent en cas de résiliation.</span>
            </div>
            <button
              data-testid="goto-cancel-canal"
              onClick={() => navigate("/resiliation-canal")}
              className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] active:scale-[0.99] text-white font-extrabold text-base py-3 px-4 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
            >
              Résilier mon abonnement
            </button>
          </motion.section>

          {/* Prélèvement — always today */}
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
              {formatDateFr(now)}
            </p>
            <p className="text-[#5a6b7a] mt-1 font-semibold" data-testid="prelevement-amount">
              Montant : 69,99 €
            </p>
          </motion.section>
        </div>
      </main>
    </div>
  );
}
