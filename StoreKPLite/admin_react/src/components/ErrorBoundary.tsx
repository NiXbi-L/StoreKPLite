import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Ловит ошибки рендера в дочерних компонентах и показывает fallback вместо белого экрана.
 * В production необработанные ошибки часто не выводятся в консоль — этот компонент их отображает.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      const { error, errorInfo } = this.state;
      return (
        <div style={{
          padding: '2rem',
          maxWidth: 800,
          margin: '2rem auto',
          fontFamily: 'system-ui, sans-serif',
          background: '#fff5f5',
          border: '1px solid #feb2b2',
          borderRadius: 8,
        }}>
          <h2 style={{ color: '#c53030', marginTop: 0 }}>Ошибка при отображении страницы</h2>
          <pre style={{
            background: '#2d3748',
            color: '#e2e8f0',
            padding: '1rem',
            borderRadius: 4,
            overflow: 'auto',
            fontSize: '0.875rem',
          }}>
            {error.toString()}
          </pre>
          {errorInfo?.componentStack && (
            <details style={{ marginTop: '1rem' }}>
              <summary style={{ cursor: 'pointer', color: '#4a5568' }}>Стек компонентов</summary>
              <pre style={{
                background: '#edf2f7',
                padding: '1rem',
                borderRadius: 4,
                overflow: 'auto',
                fontSize: '0.75rem',
                marginTop: '0.5rem',
              }}>
                {errorInfo.componentStack}
              </pre>
            </details>
          )}
          <button
            type="button"
            onClick={() => window.location.href = (process.env.PUBLIC_URL || '/admin') + '/'}
            style={{
              marginTop: '1rem',
              padding: '0.5rem 1rem',
              cursor: 'pointer',
              background: '#3182ce',
              color: 'white',
              border: 'none',
              borderRadius: 4,
            }}
          >
            На главную
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
