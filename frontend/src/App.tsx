import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ChakraProvider, extendTheme } from '@chakra-ui/react';
import { AuthProvider } from '@/contexts';
import { MainLayout, ProtectedRoute } from '@/components';
import { LoginPage, RegisterPage, DashboardPage, ProgramsPage, ProgramDetailPage, CredentialsPage, RunsPage, RunDetailPage, CatalogPage, AssetDetailPage, ModelsPage } from '@/pages';

// Extend the default Chakra theme
const theme = extendTheme({
  styles: {
    global: {
      body: {
        bg: 'gray.50',
      },
    },
  },
  fonts: {
    heading: 'Inter, system-ui, sans-serif',
    body: 'Inter, system-ui, sans-serif',
  },
  colors: {
    brand: {
      50: '#e6f2ff',
      100: '#b3d9ff',
      200: '#80bfff',
      300: '#4da6ff',
      400: '#1a8cff',
      500: '#0073e6',
      600: '#005ab3',
      700: '#004080',
      800: '#00264d',
      900: '#000d1a',
    },
  },
});

// Placeholder pages for routes
function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <h1>{title}</h1>
      <p>This page is coming soon.</p>
    </div>
  );
}

export function App() {
  return (
    <ChakraProvider theme={theme}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            {/* Protected routes */}
            <Route
              element={
                <ProtectedRoute>
                  <MainLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/catalog" element={<CatalogPage />} />
              <Route path="/programs" element={<ProgramsPage />} />
              <Route path="/programs/:id" element={<ProgramDetailPage />} />
              <Route path="/credentials" element={<CredentialsPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/models/:id" element={<AssetDetailPage />} />
              <Route path="/compositions" element={<PlaceholderPage title="Compositions" />} />
              <Route path="/compositions/:id" element={<AssetDetailPage />} />
              <Route path="/assets/:id" element={<AssetDetailPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:id" element={<RunDetailPage />} />
              <Route path="/settings" element={<PlaceholderPage title="Settings" />} />
            </Route>

            {/* Default redirect */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ChakraProvider>
  );
}
