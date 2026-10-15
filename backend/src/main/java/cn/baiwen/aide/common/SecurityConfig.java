package cn.baiwen.aide.common;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.context.annotation.*;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class SecurityConfig {
    // Admin login is a later stage. Do not create Spring's generated default user.
    @Bean UserDetailsService noDefaultUser() {
        return username -> { throw new UsernameNotFoundException("管理员登录尚未开放"); };
    }
    @Bean SecurityFilterChain security(HttpSecurity http, AppProperties properties) throws Exception {
        var filter = new OncePerRequestFilter() {
            @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
                String header = req.getHeader("Authorization");
                if (header != null && header.startsWith("Bearer ") && MessageDigest.isEqual(
                        header.substring(7).getBytes(StandardCharsets.UTF_8), properties.collectorToken().getBytes(StandardCharsets.UTF_8))) {
                    var context = SecurityContextHolder.createEmptyContext();
                    context.setAuthentication(new UsernamePasswordAuthenticationToken("collector", null,
                            List.of(new SimpleGrantedAuthority("ROLE_COLLECTOR"))));
                    SecurityContextHolder.setContext(context);
                }
                chain.doFilter(req, res);
            }
        };
        return http.sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(c -> c.ignoringRequestMatchers("/api/collector/batches"))
                .authorizeHttpRequests(a -> a.requestMatchers("/api/health", "/api/shikigami", "/api/rankings", "/api/shikigami/*/statistics").permitAll()
                        .requestMatchers("/api/collector/batches").hasRole("COLLECTOR").anyRequest().denyAll())
                .exceptionHandling(e -> e.authenticationEntryPoint((req,res,ex) -> res.setStatus(401))
                        .accessDeniedHandler((req,res,ex) -> res.setStatus(403)))
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class).build();
    }
}
