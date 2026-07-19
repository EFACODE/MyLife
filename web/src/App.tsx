import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

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
            {/* Feature routes (T10.2–T10.9) are added here. */}
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
