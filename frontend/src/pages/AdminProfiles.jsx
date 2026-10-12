import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Plus,
  Pencil,
  Trash2,
  X,
  Save,
  Users,
  Upload,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { api, formatApiErrorDetail } from "@/lib/apiClient";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/components/BrandLogo";

const empty = { email: "", phone: "", name: "", iban_last4: "" };

export default function AdminProfiles() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

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
    if (!editing.email.trim() && !editing.phone.trim()) {
      toast.error("Email ou téléphone obligatoire.");
      return;
    }
    setSaving(true);
    try {
      const body = {
        email: editing.email.trim(),
        phone: editing.phone.trim(),
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
    const label = p.email || p.phone;
    if (!window.confirm(`Supprimer le profil "${label}" ?`)) return;
    try {
      await api.delete(`/admin/profiles/${p.id}`);
      toast.success("Profil supprimé");
      await load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const onImport = async (e) => {
    e.preventDefault();
    if (!importText.trim() && !importFile) {
      toast.error("Collez du texte ou sélectionnez un fichier.");
      return;
    }
    setImporting(true);
    setImportResult(null);
    try {
      let res;
      if (importFile) {
        const formData = new FormData();
        formData.append("file", importFile);
        res = await api.post("/admin/profiles/import-file", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } else {
        res = await api.post("/admin/profiles/import", { text: importText });
      }
      setImportResult(res.data);
      toast.success(
        `${res.data.created} créé(s), ${res.data.updated} mis à jour, ${res.data.errors.length} erreur(s)`
      );
      await load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setImporting(false);
    }
  };

  const resetImport = () => {
    setImportOpen(false);
    setImportText("");
    setImportFile(null);
    setImportResult(null);
  };

  const filtered = profiles.filter((p) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      (p.email || "").toLowerCase().includes(q) ||
      (p.phone || "").toLowerCase().includes(q) ||
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

      <main className="max-w-5xl mx-auto px-5 py-8 md:py-12">
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
              Gérez les utilisateurs autorisés (email / téléphone → nom + 4 derniers chiffres IBAN).
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              data-testid="admin-import-open"
              onClick={() => setImportOpen(true)}
              className="inline-flex items-center gap-2 rounded-full border-2 border-[#164194] text-[#164194] hover:bg-[#164194] hover:text-white font-bold px-5 py-3 transition-all"
            >
              <Upload size={20} /> Importer
            </button>
            <button
              data-testid="admin-new-profile"
              onClick={() => setEditing({ ...empty })}
              className="inline-flex items-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold px-5 py-3 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
            >
              <Plus size={20} /> Nouveau profil
            </button>
          </div>
        </motion.div>

        <div className="bg-white rounded-2xl shadow-[0_8px_24px_rgba(22,65,148,0.08)] p-5">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher par email, téléphone ou nom..."
            data-testid="admin-search"
            className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 transition-colors"
          />

          {loading ? (
            <p className="text-[#5a6b7a] py-6 text-center">Chargement...</p>
          ) : filtered.length === 0 ? (
            <p className="text-[#5a6b7a] py-10 text-center" data-testid="admin-empty">
              {profiles.length === 0
                ? "Aucun profil enregistré. Cliquez sur « Nouveau profil » ou « Importer » pour commencer."
                : "Aucun résultat pour cette recherche."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[#8a98a6] text-xs uppercase tracking-wide border-b border-[#eef3f7]">
                    <th className="py-3 pr-4">Email</th>
                    <th className="py-3 pr-4">Téléphone</th>
                    <th className="py-3 pr-4">Nom du titulaire</th>
                    <th className="py-3 pr-4">IBAN (4 derniers)</th>
                    <th className="py-3 pr-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody data-testid="admin-profiles-table">
                  {filtered.map((p) => (
                    <tr key={p.id} className="border-b border-[#eef3f7]">
                      <td className="py-3 pr-4 text-[#17334d] break-all">{p.email || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d]">{p.phone || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d] font-semibold">{p.name || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d] tracking-wider">
                        {p.iban_last4 ? `•••• ${p.iban_last4}` : "—"}
                      </td>
                      <td className="py-3 pr-2 text-right">
                        <div className="inline-flex items-center gap-2">
                          <button
                            data-testid={`admin-edit-${p.id}`}
                            onClick={() => setEditing({ ...p })}
                            className="p-2 rounded-lg hover:bg-[#eef3f7] text-[#164194]"
                            aria-label="Modifier"
                          >
                            <Pencil size={18} />
                          </button>
                          <button
                            data-testid={`admin-delete-${p.id}`}
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

      {/* Edit / Create modal */}
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
              <label className="block text-[#17334d] font-bold mb-1">Email</label>
              <input
                data-testid="admin-form-email"
                type="email"
                value={editing.email}
                onChange={(e) => setEditing({ ...editing, email: e.target.value })}
                placeholder="vincentmarie@gmail.com"
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-3 transition-colors"
              />
              <label className="block text-[#17334d] font-bold mb-1">Téléphone</label>
              <input
                data-testid="admin-form-phone"
                type="tel"
                value={editing.phone}
                onChange={(e) => setEditing({ ...editing, phone: e.target.value })}
                placeholder="0612345678"
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-3 transition-colors"
              />
              <p className="text-[#8a98a6] text-xs mb-4">
                Au moins l&apos;email <strong>ou</strong> le téléphone est obligatoire.
              </p>
              <label className="block text-[#17334d] font-bold mb-1">Nom du titulaire</label>
              <input
                data-testid="admin-form-name"
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                placeholder="Vincent MARIE"
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

      {/* Import modal */}
      {importOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl w-full max-w-xl p-6 relative max-h-[90vh] overflow-y-auto"
          >
            <button
              onClick={resetImport}
              className="absolute right-4 top-4 text-[#17334d]"
              aria-label="Fermer"
            >
              <X size={24} />
            </button>
            <h2 className="text-[#17334d] font-extrabold text-2xl mb-2 flex items-center gap-2">
              <Upload size={24} /> Importer des utilisateurs
            </h2>
            <p className="text-[#5a6b7a] text-sm mb-4">
              Tous les formats sont acceptés : CSV, TSV, point-virgule, pipe, espaces... Une ligne
              par utilisateur. Chaque ligne doit contenir au moins un email ou un téléphone. Les
              lignes commençant par <code>#</code> sont ignorées.
            </p>
            <div className="bg-[#f3f7fa] border border-[#dde6ee] rounded-lg p-3 text-xs text-[#17334d] mb-4 font-mono">
              <p className="text-[#8a98a6] mb-1">Exemples :</p>
              <p>email,phone,name,iban_last4</p>
              <p>vincentmarie@gmail.com,0612345678,Vincent MARIE,4521</p>
              <p>jean@test.fr;0611112222;Jean DUPONT;1234</p>
              <p>alice@domain.com | 0633334444 | Alice MARTIN | 9876</p>
              <p>thomas@test.fr 0677778888 Thomas PETIT 3344</p>
            </div>

            <form onSubmit={onImport}>
              <label className="block text-[#17334d] font-bold mb-1 flex items-center gap-2">
                <FileText size={16} /> Fichier (.csv, .txt, .tsv)
              </label>
              <input
                data-testid="admin-import-file"
                type="file"
                accept=".csv,.txt,.tsv,text/*"
                onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2 text-[#17334d] mb-4 transition-colors"
              />
              <label className="block text-[#17334d] font-bold mb-1">Ou coller le texte</label>
              <textarea
                data-testid="admin-import-text"
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                rows={8}
                placeholder="Collez ici les lignes à importer..."
                className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 font-mono text-sm transition-colors"
              />
              <button
                type="submit"
                data-testid="admin-import-submit"
                disabled={importing}
                className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold text-lg py-3.5 transition-all disabled:opacity-60 shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
              >
                <Upload size={18} /> {importing ? "Import en cours..." : "Lancer l'import"}
              </button>
            </form>

            {importResult && (
              <div
                data-testid="admin-import-result"
                className="mt-5 bg-[#f3f7fa] rounded-lg p-4 border border-[#dde6ee]"
              >
                <p className="text-[#17334d] font-bold mb-2">Résultat de l&apos;import</p>
                <p className="text-sm text-[#17334d]">
                  <strong>{importResult.created}</strong> créé(s),{" "}
                  <strong>{importResult.updated}</strong> mis à jour,{" "}
                  <strong>{importResult.errors.length}</strong> erreur(s) sur{" "}
                  <strong>{importResult.total}</strong> ligne(s).
                </p>
                {importResult.errors.length > 0 && (
                  <ul className="mt-2 text-xs text-[#c0392b] space-y-1 max-h-32 overflow-y-auto">
                    {importResult.errors.map((e, i) => (
                      <li key={i}>
                        Ligne {e.line} : {e.error}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
}
