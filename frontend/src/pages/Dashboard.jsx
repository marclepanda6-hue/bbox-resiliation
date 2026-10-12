import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { LogOut, User, Landmark, Tv, CalendarClock, Pencil, X, Shield } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, formatApiErrorDetail } from "@/lib/apiClient";
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
  const { user, setUser, logout } = useAuth();
  const [prelevements, setPrelevements] = useState(null);
  const [editing, setEditing] = useState(false);
  const [nom, setNom] = useState("");
  const [prenom, setPrenom] = useState("");
  const [iban, setIban] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user === false) navigate("/");
    if (user) {
      setNom(user.nom || "");
      setPrenom(user.prenom || "");
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

  const saveProfile = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { nom, prenom };
      if (iban.trim()) body.iban = iban.trim();
      const res = await api.put("/profile", body);
      setUser(res.data.user);
      setIban("");
      setEditing(false);
      toast.success("Informations mises à jour");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const fullName = user.name || [user.prenom, user.nom].filter(Boolean).join(" ") || "Non renseigné";
  const latestDate = prelevements?.latest;
  const isAdmin = user.role === "admin";
  const managedByAdmin = Boolean(user.managed_by_admin);

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
          Bienvenue {user.prenom || user.email}, voici le récapitulatif de votre compte.
        </p>

        <div className="grid sm:grid-cols-2 gap-4">
          {/* Titulaire */}
          <motion.section
            data-testid="section-titulaire"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="bg-white rounded-2xl p-5 shadow-[0_8px_24px_rgba(22,65,148,0.08)] relative"
          >
            {!managedByAdmin && (
              <button
                data-testid="edit-profile-button"
                onClick={() => setEditing(true)}
                className="absolute right-4 top-4 text-[#164194] hover:text-[#0f2d66] flex items-center gap-1 text-sm font-semibold"
              >
                <Pencil size={16} /> Modifier
              </button>
            )}
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

      {/* Edit profile modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl w-full max-w-md p-6 relative"
          >
            <button
              onClick={() => setEditing(false)}
              className="absolute right-4 top-4 text-[#17334d]"
              aria-label="Fermer"
            >
              <X size={24} />
            </button>
            <h2 className="text-[#17334d] font-extrabold text-2xl mb-5">Mes informations</h2>
            <form onSubmit={saveProfile}>
              <label className="block text-[#17334d] font-bold mb-1">Prénom</label>
              <input
                data-testid="edit-prenom"
                value={prenom}
                onChange={(e) => setPrenom(e.target.value)}
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 transition-colors"
              />
              <label className="block text-[#17334d] font-bold mb-1">Nom</label>
              <input
                data-testid="edit-nom"
                value={nom}
                onChange={(e) => setNom(e.target.value)}
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 transition-colors"
              />
              <label className="block text-[#17334d] font-bold mb-1">IBAN</label>
              <input
                data-testid="edit-iban"
                value={iban}
                onChange={(e) => setIban(e.target.value)}
                placeholder={user.has_iban ? user.iban_masked : "FR76 ...."}
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-1 transition-colors"
              />
              <p className="text-[#8a98a6] text-xs mb-5">
                Votre IBAN est stocké de façon sécurisée et affiché masqué.
              </p>
              <button
                type="submit"
                data-testid="save-profile"
                disabled={saving}
                className="w-full rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold text-lg py-3.5 transition-all disabled:opacity-60 shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
              >
                {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
            </form>
          </motion.div>
        </div>
      )}
    </div>
  );
}
