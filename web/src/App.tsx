import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AssistantPage } from "./pages/assistant/AssistantPage";
import { AuditPage } from "./pages/audit/AuditPage";
import { ConsentPage } from "./pages/consent/ConsentPage";
import { FinancePage } from "./pages/finance/FinancePage";
import { ForecastPage } from "./pages/forecast/ForecastPage";
import { GoalsPage } from "./pages/goals/GoalsPage";
import { HealthPage } from "./pages/health/HealthPage";
import { HomePage } from "./pages/HomePage";
import { KnowledgePage } from "./pages/knowledge/KnowledgePage";
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
            <Route path="/finance" element={<FinancePage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/goals" element={<GoalsPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/assistant" element={<AssistantPage />} />
            <Route path="/forecast" element={<ForecastPage />} />
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
