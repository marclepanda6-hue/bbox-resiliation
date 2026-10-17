import { useEffect, useRef, useState, useCallback } from "react";
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
  Download,
  FileText,
  ChevronLeft,
  ChevronRight,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { api, API, describeApiError } from "@/lib/apiClient";
import { useAuth } from "@/context/AuthContext";
import { BrandLogo } from "@/components/BrandLogo";

const empty = {
  email: "",
  phone: "",
  name: "",
  iban_last4: "",
  bic: "",
  bank_name: "",
  address: "",
  postal_code: "",
  city: "",
  birth_year: "",
};

const PAGE_SIZE = 50;

// Decorative emoji markers (admin view "with emojis" — clients never see these).
const EMO = {
  name: "\u{1F464}",
  email: "\u{1F4E7}",
  phone: "\u{1F4F1}",
  address: "\u{1F3E0}",
  postal: "\u{1F4EE}",
  birth: "\u{1F4C5}",
};

export default function AdminProfiles() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [profiles, setProfiles] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(() => new Set());

  // Import state
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importJob, setImportJob] = useState(null);

  // Delete range state
  const [rangeOpen, setRangeOpen] = useState(false);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");

  const pollRef = useRef(null);

  const load = useCallback(async (p = page, q = query) => {
    setLoading(true);
    try {
      const res = await api.get("/admin/profiles", {
        params: { skip: p * PAGE_SIZE, limit: PAGE_SIZE, q },
      });
      setProfiles(res.data.profiles || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      toast.error(describeApiError(err) || "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, [page, query]);

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
    if (user) load(page, query);
  }, [user, page]);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => {
      setPage(0);
      load(0, query);
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => () => pollRef.current && clearInterval(pollRef.current), []);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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
        bic: (editing.bic || "").trim().toUpperCase(),
        bank_name: (editing.bank_name || "").trim(),
        address: (editing.address || "").trim(),
        postal_code: (editing.postal_code || "").trim(),
        city: (editing.city || "").trim(),
        birth_year: (editing.birth_year || "").trim(),
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
      toast.error(describeApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (p) => {
    const label = p.name || p.email || p.phone;
    if (!window.confirm(`Supprimer le profil "${label}" ?`)) return;
    try {
      await api.delete(`/admin/profiles/${p.id}`);
      toast.success("Profil supprimé");
      setSelected((s) => {
        const n = new Set(s);
        n.delete(p.id);
        return n;
      });
      await load();
    } catch (err) {
      toast.error(describeApiError(err));
    }
  };

  const toggleSelect = (id) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const allPageSelected = profiles.length > 0 && profiles.every((p) => selected.has(p.id));
  const toggleSelectPage = () => {
    setSelected((s) => {
      const n = new Set(s);
      if (allPageSelected) profiles.forEach((p) => n.delete(p.id));
      else profiles.forEach((p) => n.add(p.id));
      return n;
    });
  };

  const onDeleteSelected = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!window.confirm(`Supprimer ${ids.length} profil(s) sélectionné(s) ?`)) return;
    try {
      const res = await api.post("/admin/profiles/delete-bulk", { ids });
      toast.success(`${res.data.deleted} profil(s) supprimé(s)`);
      setSelected(new Set());
      await load();
    } catch (err) {
      toast.error(describeApiError(err));
    }
  };

  const onDeleteAll = async () => {
    if (
      !window.confirm(
        `Vider TOUTE la base (${total} profil(s)) ? Cette action est irréversible.`
      )
    )
      return;
    if (!window.confirm("Confirmez-vous définitivement la suppression de TOUS les profils ?"))
      return;
    try {
      const res = await api.delete("/admin/profiles/all");
      toast.success(`${res.data.deleted} profil(s) supprimé(s)`);
      setSelected(new Set());
      setPage(0);
      await load(0, query);
    } catch (err) {
      toast.error(describeApiError(err));
    }
  };

  const onDeleteRange = async (e) => {
    e.preventDefault();
    const start = parseInt(rangeStart, 10);
    const end = parseInt(rangeEnd, 10);
    if (!start || !end || end < start) {
      toast.error("Plage invalide (ex : 1 à 28000).");
      return;
    }
    if (!window.confirm(`Supprimer les lignes ${start} à ${end} ?`)) return;
    try {
      const res = await api.post("/admin/profiles/delete-range", { start, end });
      toast.success(`${res.data.deleted} profil(s) supprimé(s)`);
      setRangeOpen(false);
      setRangeStart("");
      setRangeEnd("");
      setSelected(new Set());
      setPage(0);
      await load(0, query);
    } catch (err) {
      toast.error(describeApiError(err));
    }
  };

  // ---- Import with background job + progress polling ----
  const pollJob = (jobId) => {
    pollRef.current && clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.get(`/admin/profiles/import-status/${jobId}`);
        const job = res.data;
        setImportJob(job);
        if (job.status === "done" || job.status === "error") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setImporting(false);
          if (job.status === "done") {
            toast.success(
              `Import terminé : ${job.created} créé(s), ${job.updated} mis à jour, ${job.errors} erreur(s)`
            );
          } else {
            toast.error(job.message || "Import en erreur");
          }
          await load(0, query);
          setPage(0);
        }
      } catch (err) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setImporting(false);
        toast.error(describeApiError(err));
      }
    }, 800);
  };

  const onImport = async (e) => {
    e.preventDefault();
    if (!importText.trim() && !importFile) {
      toast.error("Collez du texte ou sélectionnez un fichier.");
      return;
    }
    setImporting(true);
    setImportJob({ status: "parsing", total: 0, processed: 0, created: 0, updated: 0, errors: 0 });
    try {
      let res;
      if (importFile) {
        const formData = new FormData();
        formData.append("file", importFile);
        res = await api.post("/admin/profiles/import-file", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 0,
        });
      } else {
        res = await api.post("/admin/profiles/import", { text: importText }, { timeout: 0 });
      }
      pollJob(res.data.job_id);
    } catch (err) {
      setImporting(false);
      toast.error(describeApiError(err));
    }
  };

  const resetImport = () => {
    if (importing) return;
    setImportOpen(false);
    setImportText("");
    setImportFile(null);
    setImportJob(null);
  };

  const onExport = (format) => {
    const a = document.createElement("a");
    a.href = `${API}/admin/profiles/export?format=${format}`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success(`Export ${format.toUpperCase()} lancé`);
  };

  const pct = importJob && importJob.total > 0
    ? Math.min(100, Math.round((importJob.processed / importJob.total) * 100))
    : 0;

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

      <main className="max-w-6xl mx-auto px-4 sm:px-5 py-8 md:py-10">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-start justify-between gap-3 mb-6"
        >
          <div>
            <h1 className="text-[#17334d] font-extrabold text-3xl md:text-4xl flex items-center gap-3">
              <Users size={32} /> Panel admin
            </h1>
            <p className="text-[#5a6b7a] mt-1" data-testid="admin-total">
              {total.toLocaleString("fr-FR")} profil(s) enregistré(s)
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              data-testid="admin-export-csv"
              onClick={() => onExport("csv")}
              className="inline-flex items-center gap-2 rounded-full border-2 border-[#1b7a46] text-[#1b7a46] hover:bg-[#1b7a46] hover:text-white font-bold px-4 py-2.5 transition-all"
            >
              <Download size={18} /> Export CSV
            </button>
            <button
              data-testid="admin-export-txt"
              onClick={() => onExport("txt")}
              className="inline-flex items-center gap-2 rounded-full border-2 border-[#1b7a46] text-[#1b7a46] hover:bg-[#1b7a46] hover:text-white font-bold px-4 py-2.5 transition-all"
            >
              <Download size={18} /> Export TXT
            </button>
            <button
              data-testid="admin-import-open"
              onClick={() => setImportOpen(true)}
              className="inline-flex items-center gap-2 rounded-full border-2 border-[#164194] text-[#164194] hover:bg-[#164194] hover:text-white font-bold px-4 py-2.5 transition-all"
            >
              <Upload size={18} /> Importer
            </button>
            <button
              data-testid="admin-new-profile"
              onClick={() => setEditing({ ...empty })}
              className="inline-flex items-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold px-4 py-2.5 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
            >
              <Plus size={18} /> Nouveau
            </button>
          </div>
        </motion.div>

        {/* Toolbar: search + bulk delete actions */}
        <div className="bg-white rounded-2xl shadow-[0_8px_24px_rgba(22,65,148,0.08)] p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Rechercher (email, téléphone, nom, ville...)"
              data-testid="admin-search"
              className="flex-1 min-w-[220px] rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
            />
            <button
              data-testid="admin-delete-selected"
              onClick={onDeleteSelected}
              disabled={selected.size === 0}
              className="inline-flex items-center gap-2 rounded-lg border-2 border-[#c4521f] text-[#c4521f] font-bold px-3 py-2.5 hover:bg-[#fdebd3] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Trash2 size={18} /> Sélection ({selected.size})
            </button>
            <button
              data-testid="admin-delete-range-open"
              onClick={() => setRangeOpen(true)}
              className="inline-flex items-center gap-2 rounded-lg border-2 border-[#c4521f] text-[#c4521f] font-bold px-3 py-2.5 hover:bg-[#fdebd3] transition-all"
            >
              <Trash2 size={18} /> Plage
            </button>
            <button
              data-testid="admin-delete-all"
              onClick={onDeleteAll}
              disabled={total === 0}
              className="inline-flex items-center gap-2 rounded-lg bg-[#c4521f] text-white font-bold px-3 py-2.5 hover:bg-[#a9441a] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Trash2 size={18} /> Tout vider
            </button>
          </div>

          {loading ? (
            <p className="text-[#5a6b7a] py-10 text-center flex items-center justify-center gap-2">
              <Loader2 className="animate-spin" size={18} /> Chargement...
            </p>
          ) : profiles.length === 0 ? (
            <p className="text-[#5a6b7a] py-10 text-center" data-testid="admin-empty">
              {total === 0
                ? "Aucun profil. Cliquez sur « Importer » ou « Nouveau » pour commencer."
                : "Aucun résultat pour cette recherche."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[#8a98a6] text-xs uppercase tracking-wide border-b border-[#eef3f7]">
                    <th className="py-3 pr-2">
                      <input
                        type="checkbox"
                        checked={allPageSelected}
                        onChange={toggleSelectPage}
                        className="w-4 h-4 accent-[#164194] cursor-pointer"
                        aria-label="Tout sélectionner (page)"
                      />
                    </th>
                    <th className="py-3 pr-3">#</th>
                    <th className="py-3 pr-4">{EMO.name} Nom</th>
                    <th className="py-3 pr-4">{EMO.email} Email</th>
                    <th className="py-3 pr-4">{EMO.phone} Tél.</th>
                    <th className="py-3 pr-4">{EMO.address} Adresse</th>
                    <th className="py-3 pr-4">{EMO.postal} CP / Ville</th>
                    <th className="py-3 pr-4">{EMO.birth} Né(e)</th>
                    <th className="py-3 pr-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody data-testid="admin-profiles-table">
                  {profiles.map((p, i) => (
                    <tr
                      key={p.id}
                      className={`border-b border-[#eef3f7] ${selected.has(p.id) ? "bg-[#eef6fb]" : ""}`}
                    >
                      <td className="py-3 pr-2">
                        <input
                          type="checkbox"
                          checked={selected.has(p.id)}
                          onChange={() => toggleSelect(p.id)}
                          className="w-4 h-4 accent-[#164194] cursor-pointer"
                          aria-label="Sélectionner"
                        />
                      </td>
                      <td className="py-3 pr-3 text-[#8a98a6] tabular-nums">
                        {page * PAGE_SIZE + i + 1}
                      </td>
                      <td className="py-3 pr-4 text-[#17334d] font-semibold whitespace-nowrap">
                        {p.name || "—"}
                      </td>
                      <td className="py-3 pr-4 text-[#17334d] break-all">{p.email || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d] whitespace-nowrap">{p.phone || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d]">{p.address || "—"}</td>
                      <td className="py-3 pr-4 text-[#17334d] whitespace-nowrap">
                        {p.postal_code || p.city ? `${p.postal_code || ""} ${p.city || ""}`.trim() : "—"}
                      </td>
                      <td className="py-3 pr-4 text-[#17334d]">{p.birth_year || "—"}</td>
                      <td className="py-3 pr-2 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            data-testid={`admin-edit-${p.id}`}
                            onClick={() => setEditing({ ...empty, ...p })}
                            className="p-2 rounded-lg hover:bg-[#eef3f7] text-[#164194]"
                            aria-label="Modifier"
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            data-testid={`admin-delete-${p.id}`}
                            onClick={() => onDelete(p)}
                            className="p-2 rounded-lg hover:bg-[#fdebd3] text-[#c4521f]"
                            aria-label="Supprimer"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#eef3f7]">
              <span className="text-[#5a6b7a] text-sm">
                Page {page + 1} / {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <button
                  data-testid="admin-prev-page"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="inline-flex items-center gap-1 rounded-lg border-2 border-[#c7d1da] text-[#17334d] font-bold px-3 py-2 disabled:opacity-40 hover:bg-[#f3f7fa]"
                >
                  <ChevronLeft size={18} /> Précédent
                </button>
                <button
                  data-testid="admin-next-page"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="inline-flex items-center gap-1 rounded-lg border-2 border-[#c7d1da] text-[#17334d] font-bold px-3 py-2 disabled:opacity-40 hover:bg-[#f3f7fa]"
                >
                  Suivant <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Edit / Create modal */}
      {editing !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6 overflow-y-auto">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl w-full max-w-lg p-6 relative my-auto"
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
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-[#17334d] font-bold mb-1">{EMO.name} Nom du titulaire</label>
                  <input
                    data-testid="admin-form-name"
                    value={editing.name}
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                    placeholder="DEFOSSE YOANNE"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[#17334d] font-bold mb-1">{EMO.email} Email</label>
                  <input
                    data-testid="admin-form-email"
                    type="email"
                    value={editing.email}
                    onChange={(e) => setEditing({ ...editing, email: e.target.value })}
                    placeholder="prenom@mail.com"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[#17334d] font-bold mb-1">{EMO.phone} Téléphone</label>
                  <input
                    data-testid="admin-form-phone"
                    type="tel"
                    value={editing.phone}
                    onChange={(e) => setEditing({ ...editing, phone: e.target.value })}
                    placeholder="0612345678"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-[#17334d] font-bold mb-1">{EMO.address} Adresse</label>
                  <input
                    data-testid="admin-form-address"
                    value={editing.address}
                    onChange={(e) => setEditing({ ...editing, address: e.target.value })}
                    placeholder="13 IMPASSE DE L HAUNAY"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[#17334d] font-bold mb-1">Code postal</label>
                  <input
                    data-testid="admin-form-postal"
                    value={editing.postal_code}
                    onChange={(e) => setEditing({ ...editing, postal_code: e.target.value })}
                    placeholder="28260"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[#17334d] font-bold mb-1">Ville</label>
                  <input
                    data-testid="admin-form-city"
                    value={editing.city}
                    onChange={(e) => setEditing({ ...editing, city: e.target.value })}
                    placeholder="SAUSSAY"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[#17334d] font-bold mb-1">{EMO.birth} Année de naissance</label>
                  <input
                    data-testid="admin-form-birth"
                    value={editing.birth_year}
                    onChange={(e) =>
                      setEditing({ ...editing, birth_year: e.target.value.replace(/\D/g, "").slice(0, 4) })
                    }
                    inputMode="numeric"
                    maxLength={4}
                    placeholder="1979"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[#17334d] font-bold mb-1">4 chiffres IBAN</label>
                  <input
                    data-testid="admin-form-iban"
                    value={editing.iban_last4}
                    onChange={(e) =>
                      setEditing({ ...editing, iban_last4: e.target.value.replace(/\D/g, "").slice(0, 4) })
                    }
                    inputMode="numeric"
                    maxLength={4}
                    placeholder="4521"
                    className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d] tracking-widest transition-colors"
                  />
                </div>
              </div>
              <p className="text-[#8a98a6] text-xs mt-3 mb-4">
                Au moins l&apos;email <strong>ou</strong> le téléphone est obligatoire.
              </p>
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

      {/* Delete range modal */}
      {rangeOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl w-full max-w-md p-6 relative"
          >
            <button
              onClick={() => setRangeOpen(false)}
              className="absolute right-4 top-4 text-[#17334d]"
              aria-label="Fermer"
            >
              <X size={24} />
            </button>
            <h2 className="text-[#17334d] font-extrabold text-2xl mb-2 flex items-center gap-2">
              <Trash2 size={22} /> Supprimer une plage
            </h2>
            <p className="text-[#5a6b7a] text-sm mb-4">
              Supprime les profils par numéro de ligne (ex : de 1 à 28000). Les bornes sont incluses.
            </p>
            <form onSubmit={onDeleteRange} className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block text-[#17334d] font-bold mb-1">De la ligne</label>
                <input
                  data-testid="range-start"
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value.replace(/\D/g, ""))}
                  inputMode="numeric"
                  placeholder="1"
                  className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d]"
                />
              </div>
              <div className="flex-1">
                <label className="block text-[#17334d] font-bold mb-1">à la ligne</label>
                <input
                  data-testid="range-end"
                  value={rangeEnd}
                  onChange={(e) => setRangeEnd(e.target.value.replace(/\D/g, ""))}
                  inputMode="numeric"
                  placeholder="28000"
                  className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-2.5 text-[#17334d]"
                />
              </div>
              <button
                type="submit"
                data-testid="range-submit"
                className="rounded-lg bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold px-4 py-2.5 transition-all"
              >
                Supprimer
              </button>
            </form>
          </motion.div>
        </div>
      )}

      {/* Import modal */}
      {importOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6 overflow-y-auto">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl w-full max-w-xl p-6 relative my-auto"
          >
            <button
              onClick={resetImport}
              className="absolute right-4 top-4 text-[#17334d] disabled:opacity-40"
              aria-label="Fermer"
              disabled={importing}
            >
              <X size={24} />
            </button>
            <h2 className="text-[#17334d] font-extrabold text-2xl mb-2 flex items-center gap-2">
              <Upload size={24} /> Importer des profils
            </h2>
            <p className="text-[#5a6b7a] text-sm mb-4">
              Tous les formats sont acceptés : format par blocs (une info par ligne avec emojis,
              séparés par <code>#1</code>, <code>#2</code>...) ou format tableau (CSV, point-virgule,
              pipe, tabulation, espaces). Les doublons sont fusionnés automatiquement.
            </p>
            <div className="bg-[#0b0b0b] rounded-lg p-3 text-xs text-[#e6e6e6] mb-4 font-mono whitespace-pre-wrap leading-relaxed">
{`── #1 ──
${EMO.name} DEFOSSE YOANNE
${EMO.email} ydefosse@hotmail.com
${EMO.phone} 0652127810
${EMO.address} 13 IMPASSE DE L HAUNAY
${EMO.postal} 28260 SAUSSAY
${EMO.birth} Né(e) en 1979`}
            </div>

            {!importing && !importJob && (
              <form onSubmit={onImport}>
                <label className="text-[#17334d] font-bold mb-1 flex items-center gap-2">
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
                  rows={7}
                  placeholder="Collez ici les blocs ou lignes à importer..."
                  className="w-full rounded-lg border-2 border-[#c7d1da] focus:border-[#1aa3dd] outline-none px-4 py-3 text-[#17334d] mb-4 font-mono text-sm transition-colors"
                />
                <button
                  type="submit"
                  data-testid="admin-import-submit"
                  className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-[#c4521f] hover:bg-[#a9441a] text-white font-extrabold text-lg py-3.5 transition-all shadow-[0_6px_18px_rgba(196,82,31,0.35)]"
                >
                  <Upload size={18} /> Lancer l&apos;import
                </button>
              </form>
            )}

            {importJob && (
              <div data-testid="admin-import-progress" className="mt-2">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[#17334d] font-bold flex items-center gap-2">
                    {importing && <Loader2 className="animate-spin" size={16} />}
                    {importJob.status === "parsing" && "Analyse du fichier..."}
                    {importJob.status === "running" && "Import en cours..."}
                    {importJob.status === "done" && "Import terminé"}
                    {importJob.status === "error" && "Erreur"}
                  </span>
                  {importJob.total > 0 && (
                    <span className="text-[#5a6b7a] text-sm tabular-nums">
                      {importJob.processed.toLocaleString("fr-FR")} / {importJob.total.toLocaleString("fr-FR")}
                    </span>
                  )}
                </div>
                <div className="w-full h-3 rounded-full bg-[#eef3f7] overflow-hidden">
                  <div
                    className={`h-full transition-all ${importJob.status === "error" ? "bg-[#c0392b]" : "bg-[#1b7a46]"}`}
                    style={{ width: `${importJob.status === "done" ? 100 : pct}%` }}
                  />
                </div>
                <div className="mt-3 text-sm text-[#17334d]">
                  <strong className="text-[#1b7a46]">{(importJob.created || 0).toLocaleString("fr-FR")}</strong> créé(s) ·{" "}
                  <strong>{(importJob.updated || 0).toLocaleString("fr-FR")}</strong> mis à jour ·{" "}
                  <strong className="text-[#c0392b]">{(importJob.errors || 0).toLocaleString("fr-FR")}</strong> erreur(s)
                </div>
                {importJob.message && (
                  <p className="mt-2 text-sm text-[#c0392b] flex items-start gap-2">
                    <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {importJob.message}
                  </p>
                )}
                {importJob.error_samples && importJob.error_samples.length > 0 && (
                  <ul className="mt-2 text-xs text-[#c0392b] space-y-1 max-h-28 overflow-y-auto">
                    {importJob.error_samples.map((e, i) => (
                      <li key={i}>{e.error}</li>
                    ))}
                  </ul>
                )}
                {!importing && (
                  <button
                    onClick={resetImport}
                    className="mt-4 w-full rounded-full border-2 border-[#c7d1da] text-[#17334d] font-bold py-3 hover:bg-[#f3f7fa] transition-colors"
                  >
                    Fermer
                  </button>
                )}
              </div>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
}
