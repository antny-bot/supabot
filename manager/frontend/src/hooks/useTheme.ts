import { useState, useEffect } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    return (localStorage.getItem('theme') as ThemeMode) || 'system'
  })

  // 실제 다크모드 적용 여부 (CSS의 .dark 클래스 유무)
  const [isDark, setIsDark] = useState(() => {
    return document.documentElement.classList.contains('dark')
  })

  const changeTheme = (nextTheme: ThemeMode) => {
    setThemeState(nextTheme)
    localStorage.setItem('theme', nextTheme)
  }

  const toggle = () => {
    if (theme === 'light') changeTheme('dark')
    else if (theme === 'dark') changeTheme('system')
    else changeTheme('light')
  }

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const applyTheme = () => {
      let activeDark = false
      if (theme === 'dark') {
        activeDark = true
      } else if (theme === 'light') {
        activeDark = false
      } else {
        // system
        activeDark = mediaQuery.matches
      }

      document.documentElement.classList.toggle('dark', activeDark)
      if (activeDark) {
        document.documentElement.classList.remove('light')
      } else {
        document.documentElement.classList.add('light')
      }
      setIsDark(activeDark)
    }

    applyTheme()

    // system 테마일 때 OS 테마 실시간 변화 리스너 등록
    if (theme === 'system') {
      const listener = () => applyTheme()
      mediaQuery.addEventListener('change', listener)
      return () => mediaQuery.removeEventListener('change', listener)
    }
  }, [theme])

  return { theme, isDark, setTheme: changeTheme, toggle }
}
