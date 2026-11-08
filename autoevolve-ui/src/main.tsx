import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthGate } from './app/Auth'
import { LockedRoute } from './app/Upgrade'
import { ApiError } from './api/client'
import { ContactsPage } from './pages/ContactsPage'
import { CompanyWorkspacePage } from './pages/CompanyWorkspacePage'
import { IntegrationsPage } from './pages/IntegrationsPage'
import { SettingsPage } from './pages/SettingsPage'
import { HomePage } from './pages/HomePage'
import { OutreachPage } from './pages/OutreachPage'
import { ContentPage } from './pages/ContentPage'
import { RepliesPage } from './pages/RepliesPage'
import { MeetingsPage } from './pages/MeetingsPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { CommercialPage } from './pages/CommercialPage'
import { WorkflowsPage } from './pages/WorkflowsPage'
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
            <Route path="/commercial" element={<CommercialPage />} />
            <Route path="/workflows" element={<WorkflowsPage />} />
            <Route path="/validation" element={<Navigate to="/workflows" replace />} />
            <Route path="/home" element={<HomePage />} />
            <Route path="/contacts" element={<ContactsPage />} />
            <Route path="/outreach" element={<LockedRoute active="Outreach" title="Outreach" description="Prepare, approve, and send real cold outreach."><OutreachPage /></LockedRoute>} />
            <Route path="/replies" element={<LockedRoute active="Replies" title="Replies" description="Read and respond to inbound conversations."><RepliesPage /></LockedRoute>} />
            <Route path="/meetings" element={<LockedRoute active="Meetings" title="Meetings" description="Turn replies into booked conversations."><MeetingsPage /></LockedRoute>} />
            <Route path="/content" element={<ContentPage />} />
            <Route path="/research" element={<LockedRoute active="Research" title="Research" description="Run deeper company, market, and signal research."><CompanyWorkspacePage mode="research" /></LockedRoute>} />
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
