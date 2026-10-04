import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthGate } from './app/Auth'
import { ApiError } from './api/client'
import { ContactsPage } from './pages/ContactsPage'
import { CompanyWorkspacePage } from './pages/CompanyWorkspacePage'
import { IntegrationsPage } from './pages/IntegrationsPage'
import { SettingsPage } from './pages/SettingsPage'
import { HomePage } from './pages/HomePage'
import { OutreachPage } from './pages/OutreachPage'
import { CampaignsPage } from './pages/CampaignsPage'
import { VideoPage } from './pages/VideoPage'
import { ContentPage } from './pages/ContentPage'
import { RepliesPage } from './pages/RepliesPage'
import { MeetingsPage } from './pages/MeetingsPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { ValidationPage } from './pages/ValidationPage'
import { ServiceDiscoveryPage } from './pages/ServiceDiscoveryPage'
import { NotFoundPage } from './pages/NotFoundPage'
import './styles.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: (count, error) => count < 1 && error instanceof ApiError && error.status >= 500, staleTime: 20_000, refetchOnWindowFocus: true } } })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthGate>
          <Routes>
            <Route path="/" element={<Navigate to="/home" replace />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/services" element={<ServiceDiscoveryPage />} />
            <Route path="/validation" element={<ValidationPage />} />
            <Route path="/home" element={<HomePage />} />
            <Route path="/contacts" element={<ContactsPage />} />
            <Route path="/outreach" element={<OutreachPage />} />
            <Route path="/replies" element={<RepliesPage />} />
            <Route path="/meetings" element={<MeetingsPage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/video" element={<VideoPage />} />
            <Route path="/content" element={<ContentPage />} />
            <Route path="/research" element={<CompanyWorkspacePage mode="research" />} />
            <Route path="/companies" element={<CompanyWorkspacePage mode="companies" />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AuthGate>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
