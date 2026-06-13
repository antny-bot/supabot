# 모바일 드래그 메뉴 순서 변경 기능 구현 요청

> 이 문서는 `src/components/layout/AllMenuDrawer.tsx`에 구현된 "전체 메뉴" 드래그
> 정렬 패턴을 다른 화면/프로젝트에 재구현할 때 그대로 전달할 수 있는 구현
> 프롬프트입니다. (`DESIGN.md` → "Mobile navigation — Bottom Nav + 전체 Drawer"
> 참조)

## 개요
모바일 화면의 메뉴 목록에서, 항목을 드래그해 순서를 변경할 수 있는 기능을 구현해주세요.
다음 UX 효과가 포함되어야 합니다:

- 항목 왼쪽의 **드래그 핸들 아이콘**을 누르면 드래그가 시작됨
- 드래그 중인 항목은 **반투명(opacity ~0.5)** 처리됨
- 항목에 마우스를 올리면(hover) **배경색이 옅게 바뀌는 호버 효과**가 나타남
- 드래그한 항목을 다른 항목 위로 이동시키면, **주변 항목들이 위/아래로 부드럽게 밀려나며 자리를 비켜주는** 애니메이션이 자동으로 적용됨
- 마우스(포인터)와 모바일 터치 모두 지원

## 사용할 라이브러리
React + TypeScript + Tailwind CSS 환경 기준, `@dnd-kit` 패밀리를 사용합니다.

```bash
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

아이콘은 `lucide-react`의 `GripVertical`(드래그 핸들)을 사용합니다. 다른 아이콘 라이브러리를 쓴다면 동급 "grip/handle" 아이콘으로 대체하세요.

## 구현 구조

### 1. 정렬 가능한 개별 항목 (`SortableItem`)

`useSortable` 훅을 사용해 각 메뉴 항목을 감싸고, 반환되는 `transform`/`transition`/`isDragging`을 인라인 스타일로 적용합니다.

```tsx
import { GripVertical } from 'lucide-react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

function SortableItem({ id, label }: { id: string; label: string }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1, // 드래그 중 반투명
  }

  return (
    <li
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-xl px-3 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50"
    >
      {/* 드래그 핸들 */}
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab touch-none text-slate-300 dark:text-slate-600 active:cursor-grabbing"
        aria-label="드래그 핸들"
      >
        <GripVertical size={18} />
      </button>

      <span className="flex-1 text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
        {label}
      </span>
    </li>
  )
}
```

**핵심 포인트**
- `{...attributes} {...listeners}`를 드래그 핸들 엘리먼트에만 부여해야, 항목 전체가 아니라 핸들 아이콘을 눌렀을 때만 드래그가 시작됩니다.
- `opacity: isDragging ? 0.5 : 1`이 "드래그 중 반투명" 효과를 만듭니다.
- `hover:bg-slate-50 dark:hover:bg-slate-800/50` + `transition-colors`가 호버 효과를 만듭니다.
- `cursor-grab` / `active:cursor-grabbing` / `touch-none`은 마우스 커서 모양과 모바일 터치 시 스크롤 충돌 방지를 담당합니다.

### 2. 드래그 컨텍스트 (부모 컴포넌트)

`DndContext` + `SortableContext`로 목록 전체를 감싸고, 센서와 재정렬 로직을 설정합니다.

```tsx
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
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable'

function ReorderableMenu({ items, onOrderChange }: {
  items: string[]
  onOrderChange: (next: string[]) => void
}) {
  // 마우스: 5px 이상 움직여야 드래그 시작 (클릭 오작동 방지)
  // 터치: 150ms 누르고 있어야 드래그 시작 (스크롤과 구분)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return

    const oldIdx = items.indexOf(active.id as string)
    const newIdx = items.indexOf(over.id as string)
    const next = arrayMove(items, oldIdx, newIdx)

    onOrderChange(next) // 상위 상태/스토리지에 새 순서 반영
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={items} strategy={verticalListSortingStrategy}>
        <ul className="space-y-0.5">
          {items.map((id) => (
            <SortableItem key={id} id={id} label={id} />
          ))}
        </ul>
      </SortableContext>
    </DndContext>
  )
}
```

**핵심 포인트**
- "다른 메뉴가 위아래로 벌어지는 효과"는 별도 애니메이션 코드가 필요 없습니다. `SortableContext`의 `verticalListSortingStrategy`가 드래그 중인 항목 주변 요소들의 위치를 자동 계산하고, 각 `SortableItem`이 받는 `transform`/`transition`이 부드러운 이동 애니메이션을 만들어줍니다.
- `arrayMove(items, oldIdx, newIdx)`가 실제 배열 순서를 바꾸는 핵심 로직입니다.
- `collisionDetection={closestCenter}`는 드래그 중인 항목이 어느 항목 위에 있는지 판정하는 기본 전략입니다.

### 3. (선택) 순서 영속화

원본 구현은 변경된 순서를 `localStorage`에 저장하고, 커스텀 이벤트로 다른 컴포넌트와 동기화합니다. 대상 프로젝트의 상태 관리 방식(Context, Redux, 서버 저장 등)에 맞게 대체하세요.

```ts
const STORAGE_KEY = 'menu_order'

export function readOrder(defaultOrder: string[]): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as string[]
  } catch {}
  return [...defaultOrder]
}

export function writeOrder(order: string[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(order))
  window.dispatchEvent(new Event('menu-order-change'))
}
```

## 체크리스트
- [ ] `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` 설치
- [ ] 드래그 핸들 아이콘에만 `attributes`/`listeners` 부여
- [ ] `isDragging` 시 `opacity: 0.5` 적용
- [ ] 항목에 hover 배경 + `transition-colors` 적용
- [ ] `PointerSensor`(distance 5) + `TouchSensor`(delay 150, tolerance 5)로 마우스/터치 모두 지원
- [ ] `handleDragEnd`에서 `arrayMove`로 순서 재계산 후 상위로 전달
- [ ] (선택) 변경된 순서를 영속 저장하고 다른 화면과 동기화

## 참고 원본 구현
- `manager/frontend/src/components/layout/AllMenuDrawer.tsx` (전체 구현)
- `manager/frontend/src/lib/navPreferences.ts` (순서 저장/동기화)
- `manager/frontend/src/components/layout/BottomNav.tsx` (드로어 연동)
