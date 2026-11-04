cmake_minimum_required(VERSION 3.0.0)
project(librehome NONE)

set(PROJECT_NAME "librehome")
set(FULL_PROJECT_NAME "librehome.juujbyg")
set(DATA_DIR /)

configure_file(manifest.json.in ${CMAKE_CURRENT_BINARY_DIR}/manifest.json)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/manifest.json DESTINATION ${CMAKE_INSTALL_PREFIX})
install(FILES ${PROJECT_NAME}.apparmor DESTINATION ${DATA_DIR})
configure_file(${PROJECT_NAME}.desktop.in ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.desktop COPYONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.desktop DESTINATION ${DATA_DIR})
install(DIRECTORY assets DESTINATION ${DATA_DIR})
install(DIRECTORY qml DESTINATION ${DATA_DIR})
