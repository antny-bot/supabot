import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { GripVertical, Star, X } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { APP_NAV_ITEMS } from '../../config/pageMeta'
import type { NavKey } from '../../lib/navPreferences'
import { writeNavOrder, writeDefaultPage } from '../../lib/navPreferences'

interface Props {
  order: NavKey[]
  defaultPage: string | null
  isAdmin: boolean
  onOrderChange: (next: NavKey[]) => void
  onDefaultChange: (route: string | null) => void
  onClose: () => void
}

function SortableItem({
  navKey, isAdmin, defaultPage, onDefaultChange, onClose,
}: {
  navKey: NavKey
  isAdmin: boolean
  defaultPage: string | null
  onDefaultChange: (route: string | null) => void
  onClose: () => void
}) {
  const item = APP_NAV_ITEMS.find((n) => n.key === navKey)
  if (!item) return null
  if (item.adminOnly && !isAdmin) return null

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: navKey })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const isDefault = defaultPage === item.to

  function toggleDefault(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    const next = isDefault ? null : item!.to
    writeDefaultPage(next)
    onDefaultChange(next)
  }

  return (
    <li
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-xl px-3 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50"
    >
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab touch-none text-slate-300 dark:text-slate-600 active:cursor-grabbing"
        aria-label="드래그 핸들"
      >
        <GripVertical size={18} />
      </button>

      <Link
        to={item.to}
        onClick={onClose}
        className="flex flex-1 items-center gap-3 min-w-0"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100 dark:bg-slate-800">
          <item.Icon size={18} className="text-slate-600 dark:text-slate-300" />
        </div>
        <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{item.label}</span>
      </Link>

      <button
        onClick={toggleDefault}
        className={`shrink-0 rounded-lg p-1.5 transition-colors ${
          isDefault
            ? 'text-amber-400 dark:text-amber-300'
            : 'text-slate-300 dark:text-slate-600 hover:text-amber-400'
        }`}
        title={isDefault ? '기본 페이지 해제' : '기본 페이지로 설정'}
      >
        <Star size={16} fill={isDefault ? 'currentColor' : 'none'} />
      </button>
    </li>
  )
}

export default function AllMenuDrawer({
  order, defaultPage, isAdmin, onOrderChange, onDefaultChange, onClose,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
  )

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIdx = order.indexOf(active.id as NavKey)
    const newIdx = order.indexOf(over.id as NavKey)
    const next = arrayMove(order, oldIdx, newIdx)
    onOrderChange(next)
    writeNavOrder(next)
  }

  const visibleKeys = order.filter((k) => {
    const item = APP_NAV_ITEMS.find((n) => n.key === k)
    return item && (!item.adminOnly || isAdmin)
  })

  return (
    <>
      {/* backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* sheet */}
      <div className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl bg-white dark:bg-slate-900 shadow-2xl max-h-[80vh] flex flex-col">
        {/* header */}
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">전체 메뉴</h2>
          <p className="text-xs text-slate-400 dark:text-slate-500 flex-1 text-center">드래그로 순서 변경 · ★로 기본 페이지 설정</p>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* list */}
        <div className="overflow-y-auto flex-1 px-2 py-2">
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={visibleKeys} strategy={verticalListSortingStrategy}>
              <ul className="space-y-0.5">
                {visibleKeys.map((key) => (
                  <SortableItem
                    key={key}
                    navKey={key}
                    isAdmin={isAdmin}
                    defaultPage={defaultPage}
                    onDefaultChange={onDefaultChange}
                    onClose={onClose}
                  />
                ))}
              </ul>
            </SortableContext>
          </DndContext>
        </div>

        {/* safe area spacer */}
        <div className="safe-bottom" />
      </div>
    </>
  )
}
