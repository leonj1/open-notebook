'use client'

import { useRouter, useParams } from 'next/navigation'
import { useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowLeft, Columns2, Maximize2, PanelRight } from 'lucide-react'
import { useSourceChat } from '@/lib/hooks/useSourceChat'
import { ChatPanel } from '@/components/source/ChatPanel'
import { useNavigation } from '@/lib/hooks/use-navigation'
import { SourceDetailContent } from '@/components/source/SourceDetailContent'

type ChatLayout = 'default' | 'half' | 'full'

const layoutGridClass: Record<ChatLayout, string> = {
  default: 'grid-cols-1 lg:grid-cols-[2fr_1fr]',
  half: 'grid-cols-1 md:grid-cols-[1fr_1fr]',
  full: 'grid-cols-1',
}

export default function SourceDetailPage() {
  const router = useRouter()
  const params = useParams()
  const sourceId = decodeURIComponent(params.id as string)
  const navigation = useNavigation()
  const [chatLayout, setChatLayout] = useState<ChatLayout>('default')

  // Initialize source chat
  const chat = useSourceChat(sourceId)

  const handleBack = useCallback(() => {
    const returnPath = navigation.getReturnPath()
    router.push(returnPath)
    navigation.clearReturnTo()
  }, [navigation, router])

  return (
    <div className="flex flex-col h-screen">
      {/* Back button */}
      <div className="pt-6 pb-4 px-6 flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleBack}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {navigation.getReturnLabel()}
        </Button>

        {/* Chat layout toggle */}
        <div className="flex items-center gap-1 mb-4">
          <Button
            variant={chatLayout === 'default' ? 'secondary' : 'ghost'}
            size="icon"
            className="h-7 w-7"
            onClick={() => setChatLayout('default')}
            title="Default chat width"
          >
            <PanelRight className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant={chatLayout === 'half' ? 'secondary' : 'ghost'}
            size="icon"
            className="h-7 w-7"
            onClick={() => setChatLayout('half')}
            title="Half width chat"
          >
            <Columns2 className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant={chatLayout === 'full' ? 'secondary' : 'ghost'}
            size="icon"
            className="h-7 w-7"
            onClick={() => setChatLayout('full')}
            title="Full width chat"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Main content: Source detail + Chat */}
      <div className={`flex-1 grid gap-6 ${layoutGridClass[chatLayout]} overflow-hidden px-6 transition-all duration-200`}>
        {/* Left column - Source detail */}
        <div className={`overflow-y-auto px-4 pb-6 ${chatLayout === 'full' ? 'hidden' : ''}`}>
          <SourceDetailContent
            sourceId={sourceId}
            showChatButton={false}
            onClose={handleBack}
          />
        </div>

        {/* Right column - Chat */}
        <div className="overflow-y-auto px-4 pb-6">
          <ChatPanel
            messages={chat.messages}
            isStreaming={chat.isStreaming}
            contextIndicators={chat.contextIndicators}
            onSendMessage={(message, model) => chat.sendMessage(message, model)}
            modelOverride={chat.currentSession?.model_override}
            onModelChange={(model) => {
              if (chat.currentSessionId) {
                chat.updateSession(chat.currentSessionId, { model_override: model })
              }
            }}
            sessions={chat.sessions}
            currentSessionId={chat.currentSessionId}
            onCreateSession={(title) => chat.createSession({ title })}
            onSelectSession={chat.switchSession}
            onUpdateSession={(sessionId, title) => chat.updateSession(sessionId, { title })}
            onDeleteSession={chat.deleteSession}
            loadingSessions={chat.loadingSessions}
          />
        </div>
      </div>
    </div>
  )
}
