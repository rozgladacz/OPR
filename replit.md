# OPR Army Builder

## Overview

This is a full-stack web application for building and managing armies for tabletop wargaming, specifically designed around the OPR (One Page Rules) system. The application enables users to create custom armies, manage units and weapons, build rosters, and export them for gameplay. It features a modern React frontend with a Node.js/Express backend, using PostgreSQL for data persistence and comprehensive cost calculation algorithms for balanced army building.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **React 18** with TypeScript for type safety and modern component patterns
- **Vite** as the build tool for fast development and optimized production builds
- **Wouter** for client-side routing, providing a lightweight alternative to React Router
- **TanStack Query** for server state management, caching, and synchronization
- **shadcn/ui** component library built on Radix UI primitives for consistent, accessible UI components
- **Tailwind CSS** for utility-first styling with custom design system variables
- **Component Structure**: Pages handle routing and data fetching, shared components for reusable UI elements, custom hooks for business logic abstraction

### Backend Architecture
- **Node.js** with **Express.js** framework for RESTful API endpoints
- **TypeScript** throughout the backend for type consistency with the frontend
- **Session-based authentication** using express-session with PostgreSQL session storage
- **Passport.js** with local strategy for user authentication and bcrypt for password hashing
- **Router-based API structure** organized by feature domains (auth, armies, armory, rosters, export)
- **Middleware pattern** for authentication, error handling, and request logging

### Database Architecture
- **PostgreSQL** as the primary database with **Neon** as the serverless provider
- **Drizzle ORM** for type-safe database operations and schema management
- **Shared schema definition** between client and server using Drizzle and Zod for validation
- **Relational data model** with proper foreign key relationships between users, armies, units, weapons, abilities, and rosters
- **Migration system** using Drizzle Kit for database schema evolution

### Authentication & Authorization
- **Session-based authentication** with secure session storage in PostgreSQL
- **Passport.js integration** for authentication strategies
- **Password hashing** using bcrypt with salt for security
- **Route protection** with authentication middleware on sensitive endpoints
- **User context** maintained through React context and TanStack Query

### Cost Calculation Engine
- **OPR-compliant algorithms** implementing quality/defense/toughness modifiers
- **Dynamic cost calculation** for units based on stats, weapons, and abilities
- **Real-time cost tracking** in roster builder with point limits
- **Extensible calculation system** supporting various unit types and special rules

### State Management
- **Server state** managed by TanStack Query with automatic caching and invalidation
- **Client state** handled through React's built-in state management (useState, useContext)
- **Authentication state** centralized through custom auth context provider
- **Form state** managed by React Hook Form with Zod schema validation

## External Dependencies

### Database & Infrastructure
- **Neon PostgreSQL** - Serverless PostgreSQL database hosting
- **Drizzle ORM** - Type-safe database toolkit and query builder
- **connect-pg-simple** - PostgreSQL session store for Express sessions

### Authentication & Security
- **Passport.js** - Authentication middleware with local strategy
- **bcrypt** - Password hashing and verification
- **express-session** - Session management middleware

### Frontend UI & Styling
- **Radix UI** - Low-level UI primitives for accessibility and behavior
- **Tailwind CSS** - Utility-first CSS framework
- **Lucide React** - Icon library for consistent iconography
- **shadcn/ui** - Pre-built component library based on Radix UI

### Development & Build Tools
- **Vite** - Frontend build tool and development server
- **ESBuild** - JavaScript bundler for production builds
- **TypeScript** - Static type checking for both frontend and backend
- **Replit-specific plugins** - Development tools for Replit environment integration

### Data Management & Validation
- **Zod** - Schema validation library for runtime type checking
- **TanStack React Query** - Server state management and caching
- **React Hook Form** - Form state management and validation
- **date-fns** - Date manipulation and formatting utilities

### Additional Libraries
- **Wouter** - Minimal client-side routing
- **clsx & tailwind-merge** - Conditional CSS class management
- **class-variance-authority** - Utility for creating component variants