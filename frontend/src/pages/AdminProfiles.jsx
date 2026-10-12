import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Plus, Pencil, Trash2, X, Save, Users } from "lucide-react";
import { toast } from "sonner";
import { api, formatApiErrorDetail } from "@/lib/apiClient";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/components/BrandLogo";

const empty = { identifier: "", name: "", iban_last4: "" };

export default function AdminProfiles() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | {id?, identifier, name, iban_last4}
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");

  const load = async () => {
    try {
      const res = await api.get("/admin/profiles");
      setProfiles(res.data.profiles || []);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user === false) {
      navigate("/");
      return;
    }
    if (user && user.role !== "admin") {
      toast.error("Accès réservé aux administrateurs.");
      navigate("/espace-client");
      return;
    }
    if (user) load();
  }, [user]);

  const onSave = async (e) => {
    e.preventDefault();
    if (!editing.identifier.trim()) {
      toast.error("Identifiant obligatoire.");
      return;
    }
    setSaving(true);
    try {
      const body = {
        identifier: editing.identifier.trim(),
        name: editing.name.trim(),
        iban_last4: (editing.iban_last4 || "").trim(),
      };
      if (editing.id) {
        await api.put(`/admin/profiles/${editing.id}`, body);
        toast.success("Profil mis à jour");
      } else {
        await api.post("/admin/profiles", body);
        toast.success("Profil créé");
      }
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (p) => {
    if (!window.confirm(`Supprimer le profil "${p.identifier}" ?`)) return;
    try {
      await api.delete(`/admin/profiles/${p.id}`);
      toast.success("Profil supprimé");
      await load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const filtered = profiles.filter((p) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      p.identifier.toLowerCase().includes(q) ||
      (p.name || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="min-h-screen w-full bg-[#eef3f7] font-nunito">
      <header className="bg-white shadow-sm px-5 py-3 flex items-center justify-between">
        <BrandLogo markSize={40} />
        <button
          data-testid="admin-back"
          onClick={() => navigate("/espace-client")}
          className="flex items-center gap-1 text-[#17334d] hover:text-[#164194] font-semibold"
        >
          <ArrowLeft size={20} /> Mon espace
        </button>
      </header>

      <main className="max-w-4xl mx-auto px-5 py-8 md:py-12">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-center justify-between gap-3 mb-6"
        >
          <div>
            <h1 className="text-[#17334d] font-extrabold text-3xl md:text-4xl flex items-center gap-3">
              <Users size={32} /> Panel admin
            </h1>
            <p className="text-[#5a6b7a] mt-1">
              Gérez les correspondances identifiant → nom du titulaire + 4 derniers chiffres IBAN.
            </p>
          </div>
          <button
            data-testid="admin-new-profile"
            onClick={() => setEditing({ ...empty })}
            className="inline-flex items-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold px-5 py-3 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
          >
            <Plus size={20} /> Nouveau profil
          </button>
        </motion.div>

        <div className="bg-white rounded-2xl shadow-[0_8px_24px_rgba(22,65,148,0.08)] p-5">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher par identifiant ou nom..."
            data-testid="admin-search"
            className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 transition-colors"
          />

          {loading ? (
            <p className="text-[#5a6b7a] py-6 text-center">Chargement...</p>
          ) : filtered.length === 0 ? (
            <p className="text-[#5a6b7a] py-10 text-center" data-testid="admin-empty">
              {profiles.length === 0
                ? "Aucun profil enregistré. Cliquez sur « Nouveau profil » pour commencer."
                : "Aucun résultat pour cette recherche."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[#8a98a6] text-xs uppercase tracking-wide border-b border-[#eef3f7]">
                    <th className="py-3 pr-4">Identifiant (email / téléphone)</th>
                    <th className="py-3 pr-4">Nom du titulaire</th>
                    <th className="py-3 pr-4">IBAN (4 derniers)</th>
                    <th className="py-3 pr-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody data-testid="admin-profiles-table">
                  {filtered.map((p) => (
                    <tr key={p.id} className="border-b border-[#eef3f7]">
                      <td className="py-3 pr-4 text-[#17334d] font-semibold break-all">
                        {p.identifier}
                      </td>
                      <td className="py-3 pr-4 text-[#17334d]">{p.name || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d] tracking-wider">
                        {p.iban_last4 ? `•••• ${p.iban_last4}` : "—"}
                      </td>
                      <td className="py-3 pr-2 text-right">
                        <div className="inline-flex items-center gap-2">
                          <button
                            data-testid={`admin-edit-${p.identifier}`}
                            onClick={() => setEditing({ ...p })}
                            className="p-2 rounded-lg hover:bg-[#eef3f7] text-[#164194]"
                            aria-label="Modifier"
                          >
                            <Pencil size={18} />
                          </button>
                          <button
                            data-testid={`admin-delete-${p.identifier}`}
                            onClick={() => onDelete(p)}
                            className="p-2 rounded-lg hover:bg-[#fdebd3] text-[#c4521f]"
                            aria-label="Supprimer"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {editing !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl w-full max-w-md p-6 relative"
          >
            <button
              onClick={() => setEditing(null)}
              className="absolute right-4 top-4 text-[#17334d]"
              aria-label="Fermer"
            >
              <X size={24} />
            </button>
            <h2 className="text-[#17334d] font-extrabold text-2xl mb-5">
              {editing.id ? "Modifier le profil" : "Nouveau profil"}
            </h2>
            <form onSubmit={onSave}>
              <label className="block text-[#17334d] font-bold mb-1">
                Identifiant (email ou téléphone)
              </label>
              <input
                data-testid="admin-form-identifier"
                value={editing.identifier}
                onChange={(e) => setEditing({ ...editing, identifier: e.target.value })}
                placeholder="jean.dupont@example.com ou 0612345678"
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 transition-colors"
              />
              <label className="block text-[#17334d] font-bold mb-1">Nom du titulaire</label>
              <input
                data-testid="admin-form-name"
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                placeholder="DUPONT Jean"
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 transition-colors"
              />
              <label className="block text-[#17334d] font-bold mb-1">
                4 derniers chiffres de l&apos;IBAN
              </label>
              <input
                data-testid="admin-form-iban"
                value={editing.iban_last4}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    iban_last4: e.target.value.replace(/\D/g, "").slice(0, 4),
                  })
                }
                inputMode="numeric"
                maxLength={4}
                placeholder="1234"
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-5 tracking-widest transition-colors"
              />
              <button
                type="submit"
                data-testid="admin-form-save"
                disabled={saving}
                className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold text-lg py-3.5 transition-all disabled:opacity-60 shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
              >
                <Save size={18} /> {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
            </form>
          </motion.div>
        </div>
      )}
    </div>
  );
}
