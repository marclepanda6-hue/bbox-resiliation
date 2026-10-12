import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import FindIdentifier from "@/pages/FindIdentifier";
import Dashboard from "@/pages/Dashboard";
import CanalCancellation from "@/pages/CanalCancellation";
import AdminProfiles from "@/pages/AdminProfiles";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";
import { Toaster } from "sonner";

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Login />} />
            <Route path="/mot-de-passe-oublie" element={<ForgotPassword />} />
            <Route path="/retrouver-identifiant" element={<FindIdentifier />} />
            <Route path="/espace-client" element={<Dashboard />} />
            <Route path="/resiliation-canal" element={<CanalCancellation />} />
            <Route path="/admin/profils" element={<AdminProfiles />} />
            <Route path="/payment/success" element={<PaymentSuccess />} />
            <Route path="/payment/cancel" element={<PaymentCancel />} />
            {/* Première connexion est désactivée — redirection vers le login */}
            <Route path="/premiere-connexion" element={<Navigate to="/" replace />} />
            <Route path="/reset-password" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-center" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
