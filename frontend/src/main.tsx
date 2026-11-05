import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// 쓰는 글자 묶음만 내려받는 Pretendard 가변 글꼴
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import './index.css';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
