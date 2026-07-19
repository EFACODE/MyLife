import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AuditPage } from "./pages/audit/AuditPage";
import { ConsentPage } from "./pages/consent/ConsentPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { PrivacyPage } from "./pages/privacy/PrivacyPage";
import { CapturePage } from "./pages/timeline/CapturePage";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/" element={<HomePage />} />
            <Route path="/capture" element={<CapturePage />} />
            <Route path="/consent" element={<ConsentPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            {/* Feature routes (T10.3–T10.9) are added here. */}
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
